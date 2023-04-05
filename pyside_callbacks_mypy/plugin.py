from collections.abc import Callable
from importlib.resources import files

from mypy import errorcodes as codes
from mypy import nodes
from mypy.argmap import map_formals_to_actuals
from mypy.messages import format_type
from mypy.nodes import CallExpr
from mypy.nodes import Context
from mypy.nodes import Decorator
from mypy.nodes import MemberExpr
from mypy.nodes import StrExpr
from mypy.nodes import TypeAlias
from mypy.nodes import TypeInfo
from mypy.plugin import ClassDefContext
from mypy.plugin import Plugin
from mypy.plugin import SemanticAnalyzerPluginInterface
from mypy.subtypes import is_subtype
from mypy.types import AnyType
from mypy.types import CallableType
from mypy.types import Instance
from mypy.types import Type
from mypy.types import TypeOfAny
from mypy.types import UnboundType
from mypy.types import get_proper_type
import tomli


def _read_available_signals() -> dict[str, dict[str, list[str]]]:
    return tomli.loads(files('pyside_callbacks_mypy').joinpath('signals.toml').read_text())


def _class_instance_var(ctx: ClassDefContext, query: StrExpr) -> Type | None:
    """Fetches the instance of the attribute from the class returning None if not found"""
    for expr in ctx.cls.base_type_exprs:
        assert isinstance(expr, MemberExpr)
        if isinstance(expr.node, TypeInfo) and query.value in expr.node.names:
            return expr.node.names[query.value].type
    return None


def str_to_bound_type(s: str, ctx: Context, api: SemanticAnalyzerPluginInterface) -> Instance | None:
    """Converts a string to the bound version of the type if possible"""
    sym = api.lookup_qualified(s, ctx)

    if sym is None:
        # the symbol is not ready, so we will return None for now, and tell mypy to run again later
        api.defer()
        return None

    node = sym.node
    if isinstance(node, TypeAlias):
        assert isinstance(node.target, Instance)
        node = node.target.type
    if not isinstance(node, TypeInfo):
        # this will ignore both TypeVar and Any types
        return None
    any_type = AnyType(TypeOfAny.from_omitted_generics)

    # return a concrete instance of the type specified
    return Instance(node, [any_type] * len(node.defn.type_vars))


def _signal_to_args(ctx: ClassDefContext, widget_type: str, signal_name: str) -> list[Instance | None]:
    """ Lookup the types for a given widget type and signal name. """
    return [
        str_to_bound_type(type_as_str, ctx.cls, ctx.api)
        for type_as_str in _read_available_signals()[widget_type][signal_name]
    ]


def verify_callback_signatures(ctx: ClassDefContext) -> None:
    for def_ in ctx.cls.defs.body:  # tranversing all the definitions in the class
        if not isinstance(def_, Decorator):
            continue

        for index, decorator in enumerate(def_.original_decorators):
            if not isinstance(decorator, CallExpr):
                continue
            assert isinstance(decorator.callee, MemberExpr)
            if "widget_event" != decorator.callee.name:
                # only select the decorator for 'widget_event'
                continue
            if def_.func.type is None:
                # do not type check if there are no type-hints
                continue
            if not all(
                d.callee.name == "widget_event"
                    if isinstance(d, CallExpr) and isinstance(d.callee, MemberExpr) else
                False
                for d in def_.original_decorators
            ):
                ctx.api.fail("Pyside Callbacks may only be decorated by widget_event", def_)
                continue

            # get the widget and signal names
            widget_expr = decorator.args[0]
            signal_expr = decorator.args[1]
            if not isinstance(widget_expr, StrExpr) or not isinstance(signal_expr, StrExpr):
                continue  # mypy already raises error

            # get the widget instance so we can know the type
            widget_instance = _class_instance_var(ctx, widget_expr)
            if widget_instance is None:
                ctx.api.fail(f'"{ctx.cls.name}" has no attribute "{widget_expr.value}"', def_, code=codes.ATTR_DEFINED)
                continue
            if isinstance(widget_instance, AnyType):
                continue

            # determine the expected types (we also prepend an AnyType to accept the self)
            try:
                assert isinstance(widget_instance, Instance)
                emitted_types = _signal_to_args(ctx, widget_instance.type.name, signal_expr.value)
            except KeyError:
                ctx.api.fail(f'{format_type(widget_instance)} does not have signal "{signal_expr.value}"', def_)
                continue
            expected_types = [
                x
                for x in [AnyType(TypeOfAny.from_omitted_generics)] + emitted_types
                if x is not None
            ]
            assert isinstance(def_.func.type, CallableType)

            # map the signal emitted types onto the signature handling *args and **kwargs
            # note: this seems to not behave properly with keyword only (i.e. foo(self, /, b))
            actual_to_formal = map_formals_to_actuals(
                [nodes.ARG_POS] * len(expected_types),
                ["var{i}" for i in range(len(expected_types))],
                def_.func.type.arg_kinds, def_.func.type.arg_names,
                lambda i: expected_types[i]
            )

            # go through each of the signal_emitted_types and check
            for arg_num, signal_emit_type in enumerate(expected_types):
                try:
                    f_expect_name = def_.func.type.arg_names[actual_to_formal[arg_num][0]]
                    f_expect_type = def_.func.type.arg_types[actual_to_formal[arg_num][0]]
                except IndexError:
                    expected_types_str = ', '.join(format_type(x) for x in expected_types[1:])
                    ctx.api.fail(
                        f'Too many arguments for "{def_.name}"; '
                        f'Emitted signal will supply [{expected_types_str}]',
                        def_.func,
                        code=codes.CALL_ARG,
                    )
                    continue

                if f_expect_name is None:
                    continue
                if arg_num == 0 and f_expect_name != "self":
                    ctx.api.fail(f'Argument {arg_num+1} to {def_.name} should be "self"', def_)
                    continue

                # bind the type so that we can verify
                if isinstance(f_expect_type, UnboundType):
                    f_expect_bound_type = str_to_bound_type(f_expect_type.name, f_expect_type, ctx.api)
                    if f_expect_bound_type is None:
                        continue
                    f_expect_type = f_expect_bound_type
                f_expect_type = get_proper_type(f_expect_type)

                # check the type
                if not is_subtype(signal_emit_type, f_expect_type):
                    ctx.api.fail(
                        f'Argument {arg_num+1} to "{def_.name}" has incompatible type {format_type(f_expect_type)}; '
                        f'Emitted signal will expect type {format_type(signal_emit_type)}.',
                        def_.func,
                        code=codes.ARG_TYPE,
                    )


class CustomPlugin(Plugin):
    def get_class_decorator_hook(
        self, fullname: str
    ) -> Callable[[ClassDefContext], None] | None:
        if "pyside_callbacks.pyside_callbacks" in fullname:
            return verify_callback_signatures
        return None


def plugin(version: str) -> type[Plugin]:
    return CustomPlugin

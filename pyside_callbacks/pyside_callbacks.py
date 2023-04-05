from collections.abc import Callable
import functools
from typing import Any


def widget_event(widget_name: str, signal_name: str) -> Callable[[Callable[..., Any]], Callable[..., None]]:
    def decorator(f: Callable[..., Any]) -> Callable[..., None]:
        # handle multiple decorators on the same function
        if hasattr(f, "_is_widget_event"):
            f._is_widget_event.append((widget_name, signal_name))
            widget_event_handler = f._is_widget_event
        else:
            widget_event_handler = [f, (widget_name, signal_name)]

        def inner_f(self_: Any) -> None:
            _callback = widget_event_handler[0]

            for wname, sname in widget_event_handler[1:]:
                functools.reduce(
                    getattr, wname.split('.') + [sname], self_,
                ).connect(
                    functools.partial(_callback, self_)
                )
        # we mark the function as a widget event so that we can invoke the function later to connect all the events
        setattr(inner_f, "_is_widget_event", widget_event_handler)
        return inner_f
    return decorator


def pyside_callbacks(cls_: Any) -> None:
    old_init = cls_.__init__

    def _new_init(*args: Any, **kwargs: Any) -> None:
        old_init(*args, **kwargs)
        _self = args[0]
        _objs = map(lambda x: getattr(_self, x), dir(_self))
        funcs = filter(lambda x: callable(x), _objs)
        funcs = filter(lambda x: hasattr(x, "_is_widget_event"), funcs)
        list(map(lambda x: x(), funcs))
    cls_.__init__ = _new_init

    return cls_

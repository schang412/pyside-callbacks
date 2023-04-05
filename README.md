# pyside-callbacks

[![Actions status](https://github.com/schang412/pyside-callbacks/workflows/CI/badge.svg)](https://github.com/schang412/pyside-callbacks/actions)
[![pdm-managed](https://img.shields.io/badge/pdm-managed-blueviolet)](https://pdm.fming.dev)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)

GitHub repository: https://github.com/schang412/pyside-callbacks

A small library that provides utility decorators for simplifying the creation of PySide6 UI. This package also contains
a mypy plugin to assist in the type-checking the signals according to the parameters.


The QT Designer workflow with Python would look like this:
1. Use QT Designer to create `main_win.ui` file.
2. Use `uic` to compile `main_win.ui` into `main_win.py`
3. Sub-Class the class defined in `main_win.py`.
4. Connect the signals to their handlers.

```python
import main_win
from PySide6 import QtWidgets

class MyQtApp(main_win.Ui_MainWindow, QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setupUi(self)
        self.pushButton.clicked.connect(self.line_edit_return_pressed)
        self.lineEdit.returnPressed.connect(self.line_edit_return_pressed)

    def line_edit_return_pressed(self) -> None:
        cmd = self.lineEdit.text()
        if not cmd:
            return
        self.lineEdit.setText("")
        self.display.appendPlainText(cmd)
```

However, this connection method does not inherently offer type-checking and could be improved using decorators:
```python
import main_win
from PySide6 import QtWidgets

import pyside_callbacks


@pyside_callbacks.pyside_callbacks
class MyQtApp(main_win.Ui_MainWindow, QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setupUi(self)

    @pyside_callbacks.widget_event("pushButton", "clicked")
    @pyside_callbacks.widget_event("lineEdit", "returnPressed")
    def line_edit_return_pressed(self) -> None:
        cmd = self.lineEdit.text()
        if not cmd:
            return
        self.lineEdit.setText("")
        self.display.appendPlainText(cmd)
```

> Note that we need to decorate both the class and the method because we need to add a hook to the `__init__` method in order to
> register the callback to the class instance. The way that we keep track of the callbacks requires that the `widget_event` decorator
> is the outermost decorator. However, currently, the `mypy` plugin expects only `widget_event` callbacks on functions that use it.
>
> In other words, we cannot mix @widget_event with other decorators (for example, @staticmethod).

We can also include a `mypy` plugin to ensure that our signals are correct. We add the `pyside_callbacks_mypy` plugin and suppress the errors from the `uic` generated file.
```toml
[tool.mypy]
plugins = [
    "pyside_callbacks_mypy.plugin"
]
[[tool.mypy.overrides]]
module = "main_win"
ignore_errors = true
```

Adding the following lines to the example application:
```python
    @pyside_callbacks.widget_event("lineEdit", "cursorPositionChanged")
    def curpos_changed(self, b: str) -> None:
        print("changed cursor position!")
```

Then, running `mypy` we will find the errors:
```shell
example/my_app/app.py:34: error: Argument 2 to "curpos_changed" has incompatible type "str"; Emitted signal will expect type "int".  [arg-type]
example/my_app/app.py:34: error: Too many arguments for "curpos_changed"; Emitted signal will supply ["int", "int"]  [call-arg]
Found 2 errors in 1 file (checked 2 source files)
```

> Note that we have to add a type-hint to `main_win.Ui_MainWindow.setupUi` otherwise dynamic types (typing.Any) will be inferred for all the widgets.

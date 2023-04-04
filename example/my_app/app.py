import main_win
from PySide6 import QtCore
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

    @pyside_callbacks.widget_event("actionQuit", "triggered")
    def handle_quit(self) -> None:
        app_inst = QtCore.QCoreApplication.instance()
        assert app_inst is not None
        app_inst.quit()

    @pyside_callbacks.widget_event("lineEdit", "textEdited")
    def asdf(self, b: str) -> None:
        print("text was edited!")


if __name__ == '__main__':
    app = QtWidgets.QApplication()
    window = MyQtApp()
    window.show()
    app.exec()

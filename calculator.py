import re
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, Overflow, ROUND_HALF_UP, localcontext

try:
    from PyQt6.QtCore import Qt, QRegularExpression
    from PyQt6.QtGui import QColor, QFont, QFontMetrics, QRegularExpressionValidator
    from PyQt6.QtWidgets import (QApplication, QFrame, QGridLayout, QLabel,
                                 QLineEdit, QPushButton, QVBoxLayout, QWidget)
except ImportError:
    from PyQt5.QtCore import Qt, QRegularExpression
    from PyQt5.QtGui import QColor, QFont, QFontMetrics, QRegularExpressionValidator
    from PyQt5.QtWidgets import (QApplication, QFrame, QGridLayout, QLabel,
                                 QLineEdit, QPushButton, QVBoxLayout, QWidget)

MAX_INPUT_LEN = 100
MAX_DIGITS = 15
MAX_ABS_RESULT = Decimal("1e15")
ROUND_TO = Decimal("1e-10")

DISPLAY_OPS = "+−×÷"
TO_CANON = {"+": "+", "-": "-", "−": "-", "*": "*", "×": "*", "/": "/", "÷": "/"}
TO_DISPLAY = {"+": "+", "-": "−", "*": "×", "/": "÷"}
ASCII_TO_DISPLAY = str.maketrans({"*": "×", "/": "÷", "-": "−"})
DIGITS = "0123456789"

BTN = 76
GAP = 14
MARGIN = 20


class CalcError(Exception):
    def __init__(self, message, pos=None):
        super().__init__(message)
        self.message = message
        self.pos = pos


@dataclass
class Token:
    kind: str
    value: str
    pos: int


def tokenize(expr):
    tokens, i, n = [], 0, len(expr)
    while i < n:
        ch = expr[i]
        if ch.isspace():
            i += 1
        elif ch in DIGITS or ch == ".":
            start = i
            while i < n and (expr[i] in DIGITS or expr[i] == "."):
                i += 1
            text = expr[start:i]
            if text.count(".") > 1 or text == ".":
                raise CalcError(f"Số không hợp lệ: '{text}'", start)
            if sum(c in DIGITS for c in text) > MAX_DIGITS:
                raise CalcError(f"Số quá dài (tối đa {MAX_DIGITS} chữ số)", start)
            tokens.append(Token("NUM", text, start))
        elif ch in TO_CANON:
            tokens.append(Token("OP", TO_CANON[ch], i))
            i += 1
        elif ch in "()":
            tokens.append(Token(ch, ch, i))
            i += 1
        else:
            raise CalcError(f"Ký tự không hợp lệ: '{ch}'", i)
    return tokens


class Parser:
    def __init__(self, tokens, source_len):
        self.tokens = tokens
        self.i = 0
        self.end_pos = source_len

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def advance(self):
        tok = self.peek()
        self.i += 1
        return tok

    def parse(self):
        if not self.tokens:
            raise CalcError("Chưa nhập biểu thức")
        value = self.expression()
        tok = self.peek()
        if tok is not None:
            if tok.kind == ")":
                raise CalcError("Dấu ')' bị thừa", tok.pos)
            raise CalcError("Thiếu toán tử giữa hai giá trị", tok.pos)
        return value

    def expression(self):
        value = self.term()
        while (tok := self.peek()) and tok.kind == "OP" and tok.value in "+-":
            self.advance()
            rhs = self.term()
            value = value + rhs if tok.value == "+" else value - rhs
        return value

    def term(self):
        value = self.factor()
        while (tok := self.peek()) and tok.kind == "OP" and tok.value in "*/":
            self.advance()
            rhs = self.factor()
            if tok.value == "*":
                value = value * rhs
            else:
                if rhs == 0:
                    raise CalcError("Không thể chia cho 0", tok.pos)
                value = value / rhs
        return value

    def factor(self):
        tok = self.advance()
        if tok is None:
            raise CalcError("Biểu thức chưa hoàn chỉnh", self.end_pos)
        if tok.kind == "OP" and tok.value in "+-":
            value = self.factor()
            return value if tok.value == "+" else -value
        if tok.kind == "NUM":
            return Decimal(tok.value)
        if tok.kind == "(":
            value = self.expression()
            close = self.advance()
            if close is None:
                raise CalcError("Thiếu dấu ')'", tok.pos)
            if close.kind != ")":
                raise CalcError("Thiếu toán tử giữa hai giá trị", close.pos)
            return value
        if tok.kind == ")":
            raise CalcError("Thiếu số trước ')'", tok.pos)
        raise CalcError(f"'{TO_DISPLAY[tok.value]}' sai vị trí", tok.pos)


def format_decimal(value):
    if value == 0:
        return "0"
    return format(value.normalize(), "f").replace("-", "−")


def evaluate(expr):
    try:
        with localcontext() as ctx:
            ctx.prec = 50
            value = Parser(tokenize(expr), len(expr)).parse()
            if abs(value) >= MAX_ABS_RESULT:
                raise CalcError("Kết quả quá lớn")
            value = value.quantize(ROUND_TO, rounding=ROUND_HALF_UP)
    except CalcError:
        raise
    except Overflow:
        raise CalcError("Tràn số")
    except (InvalidOperation, ZeroDivisionError):
        raise CalcError("Phép tính không hợp lệ")
    except RecursionError:
        raise CalcError("Lồng ngoặc quá sâu")
    return format_decimal(value)


STYLE = """
#root { background: #000000; }
QLabel { background: transparent; color: #ffffff; }
QFrame#card { background: transparent; border: none; }

QLabel#history { color: #8e8e93; font-size: 18px; min-height: 22px; }

QLineEdit#display {
    background: transparent; border: none; color: #ffffff;
    selection-background-color: #ff9500; selection-color: #ffffff;
}

QLabel#sub                 { color: #8e8e93; font-size: 20px; min-height: 28px; }
QLabel#sub[kind="error"]   { color: #ff3b30; font-size: 14px; }
QLabel#sub[kind="warn"]    { color: #ffcc00; font-size: 14px; }

QPushButton {
    background: #333333; color: #ffffff; border: none;
    border-radius: 38px; font-size: 32px; font-weight: 500;
}
QPushButton:hover   { background: #444444; }
QPushButton:pressed { background: #555555; }

QPushButton[role="num"] {
    background: #333333; color: #ffffff; font-size: 32px;
}
QPushButton[role="num"]:hover   { background: #444444; }
QPushButton[role="num"]:pressed { background: #555555; }

QPushButton[role="top"] {
    background: #a5a5a5; color: #000000; font-size: 26px; font-weight: 500;
}
QPushButton[role="top"]:hover   { background: #b8b8b8; }
QPushButton[role="top"]:pressed { background: #d4d4d4; }

QPushButton[role="op"] {
    background: #ff9500; color: #ffffff; font-size: 36px; font-weight: 500;
}
QPushButton[role="op"]:hover   { background: #ffab3a; }
QPushButton[role="op"]:pressed { background: #cc7700; }

QToolTip {
    background: #1c1c1e; color: #ffffff; border: 1px solid #3a3a3c;
    padding: 4px 8px; border-radius: 6px;
}
"""


class Calculator(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("root")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle("Máy tính")
        width = 4 * BTN + 3 * GAP + 2 * MARGIN
        self.setFixedWidth(width)
        self.setMinimumHeight(640)
        self.resize(width, 720)
        self.just_evaluated = False
        self._build_ui()
        self.setStyleSheet(STYLE)

    def _build_ui(self):
        card = QFrame()
        card.setObjectName("card")

        self.history = QLabel("")
        self.history.setObjectName("history")
        self.history.setAlignment(Qt.AlignmentFlag.AlignRight)

        self.display = QLineEdit()
        self.display.setObjectName("display")
        self.display.setFrame(False)
        self.display.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.display.setPlaceholderText("0")
        self.display.setMaxLength(MAX_INPUT_LEN)
        self.display.setFixedHeight(120)
        font = self.display.font()
        font.setWeight(QFont.Weight.Light)
        self.display.setFont(font)
        self.display.setValidator(QRegularExpressionValidator(
            QRegularExpression(r"[0-9+\-*/×÷−().\s]*"), self))
        self.display.textEdited.connect(self._on_text_edited)
        self.display.textChanged.connect(self._on_text_changed)
        self.display.returnPressed.connect(self.calculate)

        self.sub = QLabel("")
        self.sub.setObjectName("sub")
        self.sub.setWordWrap(True)
        self.sub.setAlignment(Qt.AlignmentFlag.AlignRight)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(6, 0, 6, 4)
        card_layout.setSpacing(2)
        card_layout.addStretch(1)
        card_layout.addWidget(self.history)
        card_layout.addWidget(self.display)
        card_layout.addWidget(self.sub)

        grid = QGridLayout()
        grid.setSpacing(GAP)

        layout_spec = [
            ("AC",  0, 0, 1, 1, "top"),  ("+/−", 0, 1, 1, 1, "top"),
            ("%",   0, 2, 1, 1, "top"),  ("÷",   0, 3, 1, 1, "op"),
            ("7",   1, 0, 1, 1, "num"),  ("8",   1, 1, 1, 1, "num"),
            ("9",   1, 2, 1, 1, "num"),  ("×",   1, 3, 1, 1, "op"),
            ("4",   2, 0, 1, 1, "num"),  ("5",   2, 1, 1, 1, "num"),
            ("6",   2, 2, 1, 1, "num"),  ("−",   2, 3, 1, 1, "op"),
            ("1",   3, 0, 1, 1, "num"),  ("2",   3, 1, 1, 1, "num"),
            ("3",   3, 2, 1, 1, "num"),  ("+",   3, 3, 1, 1, "op"),
            ("0",   4, 0, 1, 2, "num"),  (",",   4, 2, 1, 1, "num"),
            ("=",   4, 3, 1, 1, "op"),
        ]

        self.buttons = {}
        for text, r, c, rs, cs, role in layout_spec:
            btn = QPushButton(text)
            btn.setProperty("role", role)
            btn.setFixedSize(BTN * cs + GAP * (cs - 1), BTN)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, t=text: self._on_button(t))
            grid.addWidget(btn, r, c, rs, cs)
            self.buttons[text] = btn

        root = QVBoxLayout(self)
        root.setContentsMargins(MARGIN, MARGIN, MARGIN, MARGIN)
        root.setSpacing(10)
        root.addWidget(card, stretch=1)
        root.addLayout(grid)

    def _fit_display_font(self):
        text = self.display.text() or self.display.placeholderText()
        available = max(self.display.width() - 10, 60)
        font = QFont(self.display.font())
        for size in range(84, 23, -4):
            font.setPixelSize(size)
            if QFontMetrics(font).horizontalAdvance(text) <= available:
                break
        self.display.setFont(font)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_display_font()

    def showEvent(self, event):
        super().showEvent(event)
        self._fit_display_font()

    def _before_cursor(self):
        return self.display.text()[:self.display.cursorPosition()]

    def _current_number(self):
        return re.search(r"[0-9.]*$", self._before_cursor()).group()

    def _insert(self, s):
        if len(self.display.text()) + len(s) > MAX_INPUT_LEN:
            self._warn(f"Tối đa {MAX_INPUT_LEN} ký tự")
            return
        self.display.insert(s)
        self.just_evaluated = False
        self._clear_status()

    def _start_fresh_if_needed(self):
        if self.just_evaluated:
            self.display.clear()
            self.history.clear()
            self.just_evaluated = False

    def _take_selection(self):
        if self.display.hasSelectedText():
            self.display.del_()

    def _set_sub(self, text, kind):
        self.sub.setText(text)
        self.sub.setProperty("kind", kind)
        self.sub.style().unpolish(self.sub)
        self.sub.style().polish(self.sub)

    def _show_error(self, msg, pos=None):
        self._set_sub("⚠  " + msg, "error")
        if pos is not None:
            self.display.setCursorPosition(pos)
            if pos < len(self.display.text()):
                self.display.setSelection(pos, 1)
        self.display.setFocus()

    def _warn(self, msg):
        self._set_sub(msg, "warn")

    def _clear_status(self):
        self._update_preview()

    def _update_preview(self):
        text = self.display.text().strip()
        body = text.lstrip("−")
        if self.just_evaluated or not any(op in body for op in DISPLAY_OPS):
            self._set_sub("", "preview")
            return
        try:
            result = evaluate(text)
        except Exception:
            self._set_sub("", "preview")
            return
        self._set_sub(f"= {result}", "preview")

    def _on_button(self, t):
        if t in DIGITS:
            self._on_digit(t)
        elif t == ",":
            self._on_dot()
        elif t in DISPLAY_OPS:
            self._on_operator(t)
        elif t == "AC":
            self._on_clear()
        elif t == "=":
            self.calculate()
        elif t == "+/−":
            self._on_toggle_sign()
        elif t == "%":
            self._on_percent()

    def _on_digit(self, d):
        self._start_fresh_if_needed()
        self._take_selection()
        if self._before_cursor().endswith(")"):
            self._insert("×")
        num = self._current_number()
        if sum(c in DIGITS for c in num) >= MAX_DIGITS:
            self._warn(f"Tối đa {MAX_DIGITS} chữ số")
            return
        if num == "0":
            if d == "0":
                return
            self.display.backspace()
        self._insert(d)

    def _on_dot(self):
        self._start_fresh_if_needed()
        self._take_selection()
        num = self._current_number()
        if "." in num:
            self._warn("Chỉ được một dấu thập phân")
            return
        if self._before_cursor().endswith(")"):
            self._insert("×0.")
        elif not num:
            self._insert("0.")
        else:
            self._insert(".")

    def _on_operator(self, op):
        self.just_evaluated = False
        self._take_selection()
        before = self._before_cursor()
        last = before[-1:]

        if op == "−" and last in ("×", "÷"):
            self._insert(op)
            return

        stripped = before.rstrip(DISPLAY_OPS)
        for _ in range(len(before) - len(stripped)):
            self.display.backspace()

        if not stripped or stripped.endswith("("):
            if op == "−":
                self._insert(op)
            else:
                self._warn(f"Không thể đặt '{op}' ở đây")
            return
        self._insert(op)

    def _on_toggle_sign(self):
        text = self.display.text()
        if not text:
            self._insert("−")
            return
        if self.just_evaluated:
            if text.startswith("−"):
                self.display.setText(text[1:])
            else:
                self.display.setText("−" + text)
            return
        match = re.search(r"(−?)([0-9.]+)$", text)
        if match:
            start = match.start()
            if match.group(1) == "−":
                self.display.setText(text[:start] + match.group(2))
            else:
                self.display.setText(text[:start] + "−" + match.group(2))
            self.display.setCursorPosition(len(self.display.text()))
            self._clear_status()

    def _on_percent(self):
        text = self.display.text()
        if not text:
            return
        try:
            if self.just_evaluated:
                val = Decimal(evaluate(text).replace("−", "-")) / 100
                self.display.setText(format_decimal(val))
                return
            match = re.search(r"(−?[0-9.]+)$", text)
            if match:
                val = Decimal(match.group(1).replace("−", "-")) / 100
                new_text = text[:match.start()] + format_decimal(val)
                self.display.setText(new_text)
                self.display.setCursorPosition(len(new_text))
                self._clear_status()
        except Exception:
            pass

    def _on_clear(self):
        self.display.clear()
        self.history.clear()
        self.just_evaluated = False
        self._clear_status()

    def _on_text_edited(self, text):
        normalized = text.translate(ASCII_TO_DISPLAY)
        if normalized != text:
            pos = self.display.cursorPosition()
            self.display.setText(normalized)
            self.display.setCursorPosition(pos)
        self.just_evaluated = False
        self._clear_status()

    def _on_text_changed(self, _text):
        self._fit_display_font()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._on_clear()
        else:
            super().keyPressEvent(event)

    def calculate(self):
        expr = self.display.text()
        if not expr.strip():
            self._show_error("Chưa nhập biểu thức")
            return
        try:
            result = evaluate(expr)
        except CalcError as e:
            self._show_error(e.message, e.pos)
            return
        except Exception as e:
            self._show_error(f"Lỗi: {e}")
            return
        self.history.setText(f"{expr.strip()} =")
        self.display.setText(result)
        self.just_evaluated = True
        self._clear_status()


def main():
    if "--test" in sys.argv:
        sys.exit(1 if run_self_tests() else 0)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = Calculator()
    window.show()
    sys.exit(app.exec())


def run_self_tests():
    ok_cases = {
        "1+2": "3", "7−10": "−3", "6×7": "42", "10÷4": "2.5",
        "2+3×4": "14", "(2+3)×4": "20", "0.1+0.2": "0.3",
        "10÷3": "3.3333333333", "−5×−2": "10", "−(3+2)": "−5",
    }
    err_cases = {
        "": "Chưa nhập", "5÷0": "chia cho 0", "5+": "chưa hoàn chỉnh",
        "×5": "sai vị trí", "(2+3": "Thiếu dấu ')'", "2+3)": "thừa",
    }
    failed = 0
    for expr, expected in ok_cases.items():
        try:
            got = evaluate(expr)
        except CalcError as e:
            got = f"ERROR: {e.message}"
        passed = got == expected
        failed += not passed
        print(f"[{'OK' if passed else 'FAIL'}] {expr!r:20} -> {got}")
    for expr, fragment in err_cases.items():
        try:
            evaluate(expr)
            failed += 1
            print(f"[FAIL] {expr!r:20} -> no error")
        except CalcError as e:
            passed = fragment in e.message
            failed += not passed
            print(f"[{'OK' if passed else 'FAIL'}] {expr!r:20} -> {e.message}")
    print(f"\n{'All passed' if not failed else f'{failed} failed'}")
    return failed


if __name__ == "__main__":
    main()
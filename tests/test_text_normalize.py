from backend.app.services.text_normalize import normalize_math_notation


def test_sqrt_simple():
    assert normalize_math_notation(r"\sqrt{16}") == "√16"


def test_sqrt_expression_wraps_in_parens():
    assert normalize_math_notation(r"\sqrt{a+b}") == "√(a+b)"


def test_cube_root():
    assert normalize_math_notation(r"\sqrt[3]{27}") == "∛27"


def test_nth_root():
    assert normalize_math_notation(r"\sqrt[4]{16}") == "4√16"


def test_frac_simple():
    assert normalize_math_notation(r"\frac{1}{2}") == "(1/2)"


def test_frac_nested_in_sqrt():
    assert normalize_math_notation(r"\sqrt{\frac{1}{4}}") == "√(1/4)"


def test_sqrt_nested_in_frac():
    assert normalize_math_notation(r"\frac{\sqrt{2}}{3}") == "(√2/3)"


def test_exponent_digit_becomes_superscript():
    assert normalize_math_notation(r"x^2") == "x²"
    assert normalize_math_notation(r"x^{10}") == "x¹⁰"


def test_exponent_non_digit_falls_back_to_parens():
    assert normalize_math_notation(r"x^{2n}") == "x^(2n)"


def test_common_symbols():
    assert normalize_math_notation(r"6 \times 6") == "6 × 6"
    assert normalize_math_notation(r"12 \div 4") == "12 ÷ 4"
    assert normalize_math_notation(r"a \pm b") == "a ± b"
    assert normalize_math_notation(r"\pi r^2") == "π r²"


def test_text_command_unwraps():
    assert normalize_math_notation(r"5 \text{cm}") == "5 cm"


def test_dollar_delimiters_removed():
    assert normalize_math_notation(r"$x^2$") == "x²"


def test_unknown_command_drops_backslash():
    assert normalize_math_notation(r"\ldots") == "ldots"


def test_plain_text_untouched():
    text = "The square of a number is the product of the number with itself."
    assert normalize_math_notation(text) == text


def test_real_gemini_sample_from_log():
    source = (
        r"Cube root of a number is the value which, when cubed, "
        r"gives the original number, it is denoted by $\sqrt[3]{x}$."
        "\n\n"
        r"e.g., Cube root of $125$ = $\sqrt[3]{125} = 5$"
    )
    result = normalize_math_notation(source)
    assert "\\sqrt" not in result
    assert "∛125" in result
    assert "∛x" in result

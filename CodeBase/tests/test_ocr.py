"""Tests for the text matching on OCR results (OCR_UI_PLAN.md O5-O7). Run with: uv run pytest"""

from mpagent.execute.ocr import Word, find, phrases

H = 10  # word height in the fake screens


def line(*words, y=40):
    """Words at (x, text); each character is 6 px wide."""
    return [Word(text, x, y, x + 6 * len(text), y + H) for x, text in words]


# a tab row: one OCR line, tabs 30 px apart, the words of one tab 4 px apart
TABS = line((10, "Home"), (64, "Insert"), (130, "P&ID"), (158, "Connector"), (242, "Layout"))
# a panel with two buttons whose names both contain "export"
PANEL = line((10, "P&ID"), (38, "exportieren"), (140, "Auswahl"), (186, "exportieren"), y=70)


def texts(hits):
    return [h.text for h in hits]


def test_a_line_splits_into_labels_at_wide_gaps():
    assert [[w.text for w in p] for p in phrases([TABS])] == [["Home"], ["Insert"], ["P&ID", "Connector"], ["Layout"]]


def test_a_whole_label_is_an_exact_match_case_and_whitespace_insensitive():
    exact, contains = find([TABS], "p&id  CONNECTOR")
    assert texts(exact) == ["P&ID Connector"] and contains == []
    hit = exact[0]
    assert (hit.left, hit.right) == (130, 158 + 6 * len("Connector")) and hit.centre == ((130 + 212) // 2, 45)


def test_contains_matches_are_the_shortest_runs_of_words_and_never_exact():
    exact, contains = find([PANEL], "Export")
    assert exact == [] and texts(contains) == ["exportieren", "exportieren"]  # two places: the caller asks UIA
    exact, contains = find([line((10, "Open"), (38, "Project"))], "Project")
    assert exact == [] and texts(contains) == ["Project"] and contains[0].left == 38  # inside "Open Project"


def test_a_label_on_two_lines_matches_as_one_name():
    upper = line((100, "Duplicate"), y=40)
    lower = line((109, "Views"), y=52)
    beside = line((300, "Views"), y=52)
    exact, contains = find([upper, lower + beside], "Duplicate Views")
    assert texts(exact) == ["Duplicate Views"] and contains == []
    assert exact[0].top == 40 and exact[0].bottom == 52 + H
    assert find([upper, beside], "Duplicate Views") == ([], [])  # not below it: two labels


def test_no_look_alike_characters_and_empty_names():
    assert find([line((10, "1-AI-1001"))], "1-A1-1001") == ([], [])
    assert find([line((10, "1-A1-1001"))], "1-A1-1001")[0]
    assert find([TABS], "   ") == ([], [])


def test_each_place_is_reported_once_in_reading_order():
    lower = line((10, "Layout"), y=90)
    exact, _ = find([lower, TABS], "Layout")
    assert [h.top for h in exact] == [40, 90]

"""
Tests for the Manage Communities page of the TugOnn students frontend.

Run:
    pytest test_manage_community.py

Run a subset:
    pytest test_manage_community.py -m tabs
    pytest test_manage_community.py -m interaction
    pytest test_manage_community.py -m mobile

Watch it run:
    pytest test_manage_community.py --headed --slowmo 500
"""

import os
import re

import pytest

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = os.getenv(
    "BASE_URL", "https://tug-onn-students-front-end-v2.vercel.app"
).rstrip("/")

VERCEL_BYPASS = os.getenv("VERCEL_BYPASS", "")

PAGE_URL = BASE_URL + "/manage-community"

TABS = [
    "All Communities",
    "Join Communities",
    "My Communities",
    "Proposed Communities",
    "My Proposals",
]

CARD_SELECTOR = "article, [class*='card'], [data-testid*='community']"

ACTION_BUTTONS = r"^(Join|Leave|View|Join Waiting List|Joined Waiting List|Share)$"

DESKTOP_VIEWPORT = {"width": 1440, "height": 900}
MOBILE_VIEWPORT = {"width": 390, "height": 844}

MIN_TAP_TARGET = 44


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    args = {
        **browser_context_args,
        "viewport": DESKTOP_VIEWPORT,
        "locale": "en-US",
    }
    if VERCEL_BYPASS:
        args["extra_http_headers"] = {
            "x-vercel-protection-bypass": VERCEL_BYPASS,
            "x-vercel-set-bypass-cookie": "true",
        }
    return args


@pytest.fixture
def cm(page):
    """Manage Communities page with console errors collected."""
    errors = []
    page.on(
        "console",
        lambda m: errors.append(f"[{m.type}] {m.text}")
        if m.type == "error" and "favicon" not in m.text
        else None,
    )
    page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))

    response = page.goto(PAGE_URL, wait_until="networkidle")
    page.console_errors = errors
    page.initial_response = response
    return page


def tab(page, name):
    """Locate a tab by its label."""
    return page.locator("button, a, [role='tab']").filter(has_text=name).first


def card_count(page):
    """Number of community cards currently rendered."""
    return page.evaluate(
        f"""() => Array.from(document.querySelectorAll({CARD_SELECTOR!r}))
              .filter(el => {{
                  const r = el.getBoundingClientRect();
                  return r.height > 80 && r.width > 200;
              }}).length"""
    )


def visible_text(page):
    return page.locator("body").inner_text()


def search_field(page):
    return page.locator("input[placeholder='Search communities']").first


# ===========================================================================
# 1. Smoke
# ===========================================================================


def test_page_opens(cm):
    """The page is served with HTTP 200."""
    assert cm.initial_response.status == 200, (
        f"Page returned {cm.initial_response.status}"
    )


def test_no_console_errors(cm):
    """The browser console is clean."""
    assert not cm.console_errors, "Console errors:\n" + "\n".join(cm.console_errors)


def test_all_tabs_present(cm):
    """All five tabs are rendered."""
    missing = [t for t in TABS if cm.get_by_text(t, exact=True).count() == 0]
    assert not missing, "Tabs missing from the page: " + ", ".join(missing)


def test_no_broken_images(cm):
    """Every community image loaded."""
    broken = cm.evaluate(
        """() => Array.from(document.images)
              .filter(i => !i.complete || i.naturalWidth === 0)
              .map(i => i.currentSrc || i.src)"""
    )
    assert not broken, "Images failed to load:\n" + "\n".join(broken)


def test_no_raw_undefined_or_nan(cm):
    """Broken-data markers must not reach visible text."""
    body = visible_text(cm)
    found = [w for w in ["undefined", "NaN", "[object Object]"] if w in body]
    assert not found, "Technical values in visible text: " + ", ".join(found)


# ===========================================================================
# 2. Tabs
# ===========================================================================


@pytest.mark.tabs
def test_tabs_change_content(cm):
    """Switching a tab genuinely rebuilds the list."""
    baseline = visible_text(cm)
    unchanged = []

    for name in TABS[1:]:
        cm.goto(PAGE_URL, wait_until="networkidle")
        tab(cm, name).click()
        cm.wait_for_timeout(1000)
        if visible_text(cm) == baseline:
            unchanged.append(name)

    assert not unchanged, "Tabs do not change content: " + ", ".join(unchanged)


@pytest.mark.tabs
@pytest.mark.xfail(reason="Known defect: tab state is not written to the URL", strict=False)
def test_active_tab_is_reflected_in_url(cm):
    """
    The active tab should be shareable and bookmarkable.
    Marked xfail against a known open defect — reports XPASS once fixed.
    """
    tab(cm, "My Communities").click()
    cm.wait_for_timeout(1000)
    assert cm.url.rstrip("/") != PAGE_URL, f"URL unchanged after switching tab: {cm.url}"


@pytest.mark.tabs
@pytest.mark.xfail(reason="Known defect: reload resets to All Communities", strict=False)
def test_tab_survives_reload(cm):
    """The selected tab should survive F5."""
    tab(cm, "My Communities").click()
    cm.wait_for_timeout(1000)
    before = visible_text(cm)

    cm.reload(wait_until="networkidle")
    cm.wait_for_timeout(1000)

    assert visible_text(cm) == before, "The active tab reset after reload"


@pytest.mark.tabs
def test_back_button_returns_to_previous_tab(page):
    """
    Switching a tab should participate in browser history.
    The page is reached from the home page first so the history is realistic.
    """
    page.goto(BASE_URL, wait_until="networkidle")
    page.goto(PAGE_URL, wait_until="networkidle")

    tab(page, "My Communities").click()
    page.wait_for_timeout(1000)

    page.go_back(wait_until="networkidle")
    page.wait_for_timeout(500)

    assert page.url.rstrip("/").startswith(PAGE_URL), (
        f"Back left the page instead of returning to the previous tab: {page.url}"
    )


# ===========================================================================
# 3. Cards and counter
# ===========================================================================


def test_showing_counter_matches_card_count(cm):
    """"Showing X-Y of Z" must match the number of rendered cards."""
    match = re.search(
        r"Showing\s+(\d+)\s*[-\u2013]\s*(\d+)\s+of\s+(\d+)", visible_text(cm)
    )
    if not match:
        pytest.skip("Counter not found")

    start, end, total = map(int, match.groups())
    shown = end - start + 1
    actual = card_count(cm)

    assert shown == actual, (
        f"Counter reports {shown} cards, {actual} are rendered"
    )
    assert end <= total, f"Range {start}-{end} exceeds the total of {total}"


def test_no_duplicate_community_cards(cm):
    """A community must not appear twice within one tab."""
    names = cm.eval_on_selector_all(
        "h2, h3, h4", "els => els.map(e => e.innerText.trim()).filter(Boolean)"
    )
    dupes = sorted({n for n in names if names.count(n) > 1})
    assert not dupes, "Duplicate community cards: " + ", ".join(dupes)


def test_card_has_exactly_one_primary_action(cm):
    """Join and Leave must never appear on the same card."""
    conflicts = cm.evaluate(
        f"""() => Array.from(document.querySelectorAll({CARD_SELECTOR!r}))
              .filter(card => {{
                  const t = card.innerText || '';
                  return /\\bJoin\\b/.test(t) && /\\bLeave\\b/.test(t);
              }})
              .map(card => (card.querySelector('h2, h3, h4')?.innerText || '(unnamed)').trim())"""
    )
    assert not conflicts, "Join and Leave on the same card: " + ", ".join(conflicts)


def test_member_counts_are_not_all_identical(cm):
    """Identical member counts across communities suggest mock data."""
    counts = re.findall(r"([\d.,]+K?)\s+members", visible_text(cm))
    if len(counts) < 2:
        pytest.skip("Not enough cards to compare")

    assert len(set(counts)) > 1, (
        f"Every community reports the same member count: {counts[0]}. "
        "This looks like mock data rather than backend values."
    )


# ===========================================================================
# 4. Search and filters
# ===========================================================================


def test_search_field_accepts_input(cm):
    """The search control itself works."""
    field = search_field(cm)
    if field.count() == 0:
        pytest.skip("Search field not found")

    field.fill("Photography")
    cm.wait_for_timeout(1000)
    assert field.input_value() == "Photography", "The search field does not accept input"


def test_search_filters_the_list(cm):
    """Typing a query must narrow the list."""
    field = search_field(cm)
    if field.count() == 0:
        pytest.skip("Search field not found")

    before = visible_text(cm)
    field.fill("Photography")
    cm.wait_for_timeout(1500)

    assert visible_text(cm) != before, "Search input did not change the list at all"


def test_empty_search_shows_a_message(cm):
    """A query with no results must explain itself, not show a blank area."""
    field = search_field(cm)
    if field.count() == 0:
        pytest.skip("Search field not found")

    field.fill("zzzqqqxxx123")
    cm.wait_for_timeout(1500)

    if card_count(cm) > 0:
        pytest.skip("Search is not filtering — covered by test_search_filters_the_list")

    body = visible_text(cm).lower()
    assert any(
        w in body for w in ["no results", "not found", "nothing", "no communities", "0 of"]
    ), "Empty search results with no message for the user"


def test_search_can_be_cleared(cm):
    """Clearing the query restores the full list."""
    field = search_field(cm)
    if field.count() == 0:
        pytest.skip("Search field not found")

    before = card_count(cm)
    field.fill("zzzqqqxxx123")
    cm.wait_for_timeout(1000)
    field.fill("")
    cm.wait_for_timeout(1500)

    assert card_count(cm) == before, "The list did not recover after clearing the search"


@pytest.mark.interaction
def test_filters_are_real_dropdowns(cm):
    """
    The category and sort controls are styled as dropdowns with a chevron.
    They must be select or combobox elements, not text inputs.
    """
    bad = cm.evaluate(
        """() => Array.from(document.querySelectorAll('input'))
              .filter(i => /All categories|Most popular/i.test(i.placeholder || ''))
              .map(i => 'placeholder "' + i.placeholder
                   + '" is a plain text input, not a select or combobox')"""
    )
    assert not bad, "Filter controls are not real dropdowns:\n" + "\n".join(bad)


# ===========================================================================
# 5. Interaction and accessibility
# ===========================================================================


@pytest.mark.interaction
def test_clickable_have_pointer_cursor(cm):
    """Primary actions must signal that they are clickable."""
    wrong = cm.evaluate(
        """() => Array.from(document.querySelectorAll("a, button, [role='button'], [role='tab']"))
              .filter(el => {
                  const r = el.getBoundingClientRect();
                  if (r.width === 0 || r.height === 0) return false;
                  return getComputedStyle(el).cursor !== 'pointer';
              })
              .map(el => el.tagName.toLowerCase() + ' "'
                   + (el.innerText || el.getAttribute('aria-label') || '').trim().slice(0, 40)
                   + '" cursor: ' + getComputedStyle(el).cursor)"""
    )
    assert not wrong, "Clickable without pointer cursor:\n" + "\n".join(sorted(set(wrong)))


@pytest.mark.interaction
def test_community_names_are_real_links(cm):
    """
    A community name that reacts to the cursor must be a link or a button,
    otherwise it is invisible to keyboard and screen reader users.
    """
    fake = cm.evaluate(
        """() => Array.from(document.querySelectorAll('h2, h3, h4'))
              .filter(el => {
                  const r = el.getBoundingClientRect();
                  if (r.width === 0) return false;
                  const c = getComputedStyle(el).cursor;
                  if (c !== 'pointer' && c !== 'text') return false;
                  return !el.closest("a, button, [role='button'], [role='link']");
              })
              .map(el => '"' + el.innerText.trim().slice(0, 40) + '" cursor: '
                   + getComputedStyle(el).cursor)"""
    )
    assert not fake, (
        "Community names react to the cursor but are neither links nor buttons:\n"
        + "\n".join(sorted(set(fake)))
    )


@pytest.mark.interaction
def test_no_contenteditable(cm):
    """Nothing outside form inputs may be editable in place."""
    editable = cm.evaluate(
        """() => Array.from(document.querySelectorAll('[contenteditable]'))
              .filter(el => el.getAttribute('contenteditable') !== 'false')
              .map(el => el.tagName.toLowerCase() + ' "'
                   + (el.innerText || '').trim().slice(0, 40) + '"')"""
    )
    assert not editable, "Elements with contenteditable:\n" + "\n".join(editable)


@pytest.mark.interaction
def test_buttons_have_accessible_name(cm):
    """Icon-only buttons need an accessible name."""
    nameless = cm.evaluate(
        """() => Array.from(document.querySelectorAll("button, [role='button']"))
              .filter(el => {
                  const r = el.getBoundingClientRect();
                  if (r.width === 0 || r.height === 0) return false;
                  const text = (el.innerText || '').trim();
                  const aria = el.getAttribute('aria-label') || el.getAttribute('title') || '';
                  const imgAlt = Array.from(el.querySelectorAll('img')).map(i => i.alt || '').join('');
                  return !text && !aria && !imgAlt;
              })
              .map((el, i) => 'Unnamed button #' + (i + 1) + ' class: '
                   + (el.className || '(none)').slice(0, 80))"""
    )
    assert not nameless, "Buttons without an accessible name:\n" + "\n".join(nameless[:15])


@pytest.mark.interaction
def test_tabs_are_keyboard_accessible(cm):
    """Tabs must be in the tab order and carry a correct role."""
    problems = []

    for name in TABS:
        info = cm.evaluate(
            """(n) => {
                const els = Array.from(document.querySelectorAll('*'));
                const el = els.find(e => e.children.length === 0 && (e.innerText || '').trim() === n);
                if (!el) return null;
                const t = el.closest("button, a, [role='tab']") || el;
                return { tag: t.tagName.toLowerCase(), role: t.getAttribute('role'), tabIndex: t.tabIndex };
            }""",
            name,
        )
        if info is None:
            continue
        if info["tabIndex"] < 0:
            problems.append(f"{name}: not reachable by keyboard")
        if info["tag"] not in ("button", "a") and info["role"] != "tab":
            problems.append(
                f"{name}: not a button or link and has no role=tab, it is a <{info['tag']}>"
            )

    assert not problems, "Tab problems:\n" + "\n".join(problems)


@pytest.mark.interaction
def test_focus_is_visible(cm):
    """Keyboard navigation needs a visible focus style."""
    cm.keyboard.press("Tab")
    style = cm.evaluate(
        """() => {
            const el = document.activeElement;
            if (!el || el === document.body) return null;
            const s = getComputedStyle(el);
            return { outline: s.outlineStyle, shadow: s.boxShadow };
        }"""
    )
    assert style is not None, "Focus did not move anywhere after Tab"
    visible = style["outline"] not in ("none", "") or style["shadow"] not in ("none", "")
    assert visible, "The focused element has no visible focus style"


@pytest.mark.interaction
def test_back_arrow_works(cm):
    """The back arrow beside the communities field must navigate somewhere."""
    before = cm.url
    arrow = cm.locator("button").filter(has=cm.locator("svg")).first
    arrow.click(timeout=5000)
    cm.wait_for_timeout(1500)

    assert cm.url != before, f"The back arrow did nothing, URL unchanged: {cm.url}"


# ===========================================================================
# 6. Responsive layout
# ===========================================================================


@pytest.mark.mobile
def test_no_horizontal_scroll_mobile(page):
    """Content must fit the viewport width."""
    page.set_viewport_size(MOBILE_VIEWPORT)
    page.goto(PAGE_URL, wait_until="networkidle")
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 1, f"Horizontal overflow on mobile: {overflow}px"


@pytest.mark.mobile
def test_tabs_reachable_on_mobile(page):
    """Five tabs must remain usable on a narrow screen."""
    page.set_viewport_size(MOBILE_VIEWPORT)
    page.goto(PAGE_URL, wait_until="networkidle")

    hidden = []
    for name in TABS:
        el = page.get_by_text(name, exact=True).first
        if el.count() == 0:
            hidden.append(f"{name}: not in DOM")
        elif not el.is_visible():
            hidden.append(f"{name}: in DOM but not visible")

    assert not hidden, "Tabs not reachable on mobile:\n" + "\n".join(hidden)


@pytest.mark.mobile
def test_action_buttons_are_44px(page):
    """Join, Leave, View and Share must meet the minimum tap target."""
    page.set_viewport_size(MOBILE_VIEWPORT)
    page.goto(PAGE_URL, wait_until="networkidle")

    small = page.evaluate(
        f"""() => Array.from(document.querySelectorAll('button, a'))
              .filter(el => new RegExp({ACTION_BUTTONS!r}).test((el.innerText || '').trim()))
              .filter(el => {{
                  const r = el.getBoundingClientRect();
                  return r.width > 0 && r.height > 0
                      && (r.width < {MIN_TAP_TARGET} || r.height < {MIN_TAP_TARGET});
              }})
              .map(el => {{
                  const r = el.getBoundingClientRect();
                  return '"' + el.innerText.trim() + '" '
                       + Math.round(r.width) + 'x' + Math.round(r.height);
              }})"""
    )
    assert not small, "Action buttons below the minimum tap target:\n" + "\n".join(
        sorted(set(small))
    )

"""
Smoke and regression tests for the TugOnn students frontend — home feed page.

Setup:
    pip install -r requirements.txt
    playwright install chromium

Run:
    pytest test_smoke_tugonn.py

Run against another deployment:
    BASE_URL="https://your-preview.vercel.app" pytest test_smoke_tugonn.py

If Vercel Deployment Protection is enabled, pass a Protection Bypass for
Automation secret:
    BASE_URL="..." VERCEL_BYPASS="<secret>" pytest test_smoke_tugonn.py
"""

import os
import re
from datetime import datetime

import pytest

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = os.getenv(
    "BASE_URL", "https://tug-onn-students-front-end-v2.vercel.app"
).rstrip("/")

VERCEL_BYPASS = os.getenv("VERCEL_BYPASS", "")

DESKTOP_VIEWPORT = {"width": 1440, "height": 900}
MOBILE_VIEWPORT = {"width": 390, "height": 844}

# Console noise that is not a defect
CONSOLE_IGNORE = [
    "favicon",
    "Download the React DevTools",
    "web-vitals",
    "ERR_BLOCKED_BY_CLIENT",
]

# Everything a user perceives as clickable
CLICKABLE = (
    "a, button, [role='button'], [role='link'], [role='tab'], "
    "[role='menuitem'], [onclick]"
)

# External content hosts that should not remain in production
EXTERNAL_IMAGE_HOSTS = ["images.unsplash.com", "i.pravatar.cc"]

MIN_TAP_TARGET = 44
MAX_LOAD_TIME_MS = 5000


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
def home(page):
    """Home page with console errors collected."""
    errors = []
    page.on(
        "console",
        lambda m: errors.append(f"[{m.type}] {m.text}")
        if m.type == "error" and not any(s in m.text for s in CONSOLE_IGNORE)
        else None,
    )
    page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
    page.on(
        "requestfailed",
        lambda r: errors.append(f"[requestfailed] {r.url} {r.failure}"),
    )

    response = page.goto(BASE_URL, wait_until="networkidle")
    page.console_errors = errors
    page.initial_response = response
    return page


def internal_links(page):
    """Unique internal links on the page."""
    return page.eval_on_selector_all(
        "a[href]",
        """els => [...new Set(
            els.map(e => e.getAttribute('href'))
               .filter(h => h && h.startsWith('/') && !h.startsWith('//'))
        )]""",
    )


def visible_text(page):
    return page.locator("body").inner_text()


# ===========================================================================
# 1. Smoke
# ===========================================================================


def test_page_returns_200(home):
    """The page is served and not blocked by deployment protection."""
    assert home.initial_response is not None, "No response from the server"
    status = home.initial_response.status
    assert status == 200, (
        f"Expected 200, got {status}. A 401 or 403 means Vercel Deployment "
        "Protection is enabled and a bypass secret is required."
    )


def test_no_console_errors(home):
    """The browser console is clean."""
    assert not home.console_errors, "Console errors:\n" + "\n".join(
        home.console_errors
    )


def test_no_broken_images(home):
    """Every image actually loaded."""
    broken = home.evaluate(
        """() => Array.from(document.images)
              .filter(i => !i.complete || i.naturalWidth === 0)
              .map(i => i.currentSrc || i.src)"""
    )
    assert not broken, "Images failed to load:\n" + "\n".join(broken)


def test_page_loads_reasonably_fast(home):
    """Rough guard against the page hanging."""
    load_time = home.evaluate(
        "() => performance.timing.loadEventEnd - performance.timing.navigationStart"
    )
    assert load_time < MAX_LOAD_TIME_MS, f"Page took {load_time} ms to load"


# ===========================================================================
# 2. Metadata and SEO
# ===========================================================================


def test_title_is_not_default(home):
    """The tab label is not the framework default."""
    title = home.title().strip()
    assert title, "Page title is empty"
    assert title.lower() not in ("create next app", "vite + react", "react app"), (
        f"Default framework title not replaced: {title}"
    )


def test_meta_description_is_not_default(home):
    """The meta description is not the framework default."""
    desc = home.locator("meta[name='description']").get_attribute("content") or ""
    assert desc.strip(), "Meta description is missing"
    assert "generated by create next app" not in desc.lower(), (
        f"Default meta description: {desc}"
    )


def test_single_h1(home):
    """Exactly one H1 per page."""
    count = home.locator("h1").count()
    assert count == 1, f"Expected exactly one H1, found {count}"


def test_html_has_lang(home):
    """Required for localisation and screen readers."""
    lang = home.locator("html").get_attribute("lang")
    assert lang, "The html element has no lang attribute"


# ===========================================================================
# 3. Regression guards
# ===========================================================================


def test_no_localhost_in_page(home):
    """
    Regression guard: a previously reported critical defect had the frontend
    pointing at localhost:4000 in production.
    """
    assert "localhost" not in home.content(), (
        "Found a localhost reference in the markup — the frontend is pointing "
        "at a local backend"
    )


def test_no_placeholder_text(home):
    """Lorem ipsum, TODO and similar must not reach production."""
    body = visible_text(home).lower()
    found = [
        w
        for w in ["lorem ipsum", "todo", "tbd", "placeholder", "asdf"]
        if w in body
    ]
    assert not found, "Placeholder text on the page: " + ", ".join(found)


def test_no_raw_undefined_or_nan(home):
    """Classic broken-data markers in visible text."""
    body = visible_text(home)
    found = [w for w in ["undefined", "NaN", "[object Object]"] if w in body]
    assert not found, "Technical values in visible text: " + ", ".join(found)


# ===========================================================================
# 4. Accessibility
# ===========================================================================


def test_images_have_alt(home):
    """Every image carries an alt attribute."""
    missing = home.evaluate(
        """() => Array.from(document.images)
              .filter(i => !i.hasAttribute('alt'))
              .map(i => i.currentSrc || i.src)"""
    )
    assert not missing, "Images without an alt attribute:\n" + "\n".join(missing)


def test_all_buttons_are_keyboard_reachable(home):
    """Nothing interactive falls out of the tab order."""
    unreachable = home.evaluate(
        f"""() => Array.from(document.querySelectorAll({CLICKABLE!r}))
              .filter(el => {{
                  const r = el.getBoundingClientRect();
                  if (r.width === 0 || r.height === 0) return false;
                  return el.tabIndex < 0;
              }})
              .map(el => '<' + el.tagName.toLowerCase() + '> "'
                   + (el.innerText || el.getAttribute('aria-label') || '').trim().slice(0, 40) + '"')"""
    )
    assert not unreachable, "Not reachable by keyboard:\n" + "\n".join(
        sorted(set(unreachable))
    )


def test_focus_is_visible(home):
    """Keyboard navigation is blind without a visible focus style."""
    home.keyboard.press("Tab")
    style = home.evaluate(
        """() => {
            const el = document.activeElement;
            if (!el || el === document.body) return null;
            const s = getComputedStyle(el);
            return { outline: s.outlineStyle, width: s.outlineWidth, shadow: s.boxShadow };
        }"""
    )
    assert style is not None, "Focus did not move anywhere after Tab"
    has_style = (
        style["outline"] not in ("none", "") or style["shadow"] not in ("none", "")
    )
    assert has_style, "The focused element has no visible focus style"


def test_buttons_have_accessible_name(home):
    """An icon button without an aria-label is mute to a screen reader."""
    nameless = home.evaluate(
        """() => Array.from(document.querySelectorAll("button, [role='button']"))
              .filter(el => {
                  const r = el.getBoundingClientRect();
                  if (r.width === 0 || r.height === 0) return false;
                  const text = (el.innerText || '').trim();
                  const aria = el.getAttribute('aria-label') || el.getAttribute('title') || '';
                  const imgAlt = Array.from(el.querySelectorAll('img')).map(i => i.alt || '').join('');
                  return !text && !aria && !imgAlt;
              })
              .map((el, i) => 'Unnamed button #' + (i + 1) + ' class: ' + (el.className || '(none)').slice(0, 80))"""
    )
    assert not nameless, "Buttons without an accessible name:\n" + "\n".join(
        nameless[:15]
    )


# ===========================================================================
# 5. Navigation and browser history
# ===========================================================================


@pytest.mark.navigation
def test_no_empty_links(home):
    """Links with href='#' or an empty target lead nowhere."""
    empty = home.eval_on_selector_all(
        "a[href]",
        """els => els
            .filter(e => ['#', '', 'javascript:void(0)'].includes(e.getAttribute('href').trim()))
            .map(e => (e.innerText || e.getAttribute('aria-label') || '(no text)').trim().slice(0, 40))""",
    )
    assert not empty, "Empty links:\n" + "\n".join(empty)


@pytest.mark.navigation
def test_all_internal_links_return_2xx(home):
    """No internal link resolves to a 4xx or 5xx."""
    links = internal_links(home)
    if not links:
        pytest.skip("No internal links found")

    broken = []
    for href in links:
        resp = home.request.get(BASE_URL + href)
        if resp.status >= 400:
            broken.append(f"{href} -> {resp.status}")

    assert not broken, "Broken links:\n" + "\n".join(broken)


@pytest.mark.navigation
def test_click_every_link_and_go_back(home):
    """
    Click each link, verify the resulting URL matches its href, verify the
    page rendered, then verify the Back button returns to the origin.
    """
    links = internal_links(home)
    if not links:
        pytest.skip("No internal links found")

    problems = []

    for href in links:
        if href in ("/", ""):
            continue

        home.goto(BASE_URL, wait_until="networkidle")
        link = home.locator(f"a[href='{href}']:visible").first

        try:
            link.scroll_into_view_if_needed(timeout=3000)
            link.click(timeout=5000)
            home.wait_for_load_state("networkidle", timeout=10000)
        except Exception as exc:
            problems.append(f"{href}: click failed, {type(exc).__name__}")
            continue

        expected = (BASE_URL + href).rstrip("/")
        if home.url.rstrip("/") != expected:
            problems.append(f"{href}: landed on {home.url}, expected {expected}")
            continue

        body_text = (visible_text(home) or "").strip()
        if len(body_text) < 50:
            problems.append(f"{href}: page is essentially empty")
        if re.search(r"\b404\b|page not found", body_text, re.IGNORECASE):
            problems.append(f"{href}: page shows a 404")

        home.go_back(wait_until="networkidle")
        if home.url.rstrip("/") != BASE_URL:
            problems.append(
                f"{href}: after Back the URL is {home.url}, expected the home page"
            )

    assert not problems, "Navigation problems:\n" + "\n".join(problems)


@pytest.mark.navigation
def test_back_button_exists_on_inner_pages(home):
    """
    Inner pages need a visible way back. The browser arrow alone traps
    mobile users.
    """
    links = internal_links(home)
    if not links:
        pytest.skip("No inner pages found")

    back_selector = (
        "[aria-label*='back' i], button:has-text('Back'), a:has-text('Back'), "
        "[data-testid*='back' i], header a[href='/']"
    )
    missing = []

    for href in links:
        home.goto(BASE_URL + href, wait_until="networkidle")
        if home.locator(back_selector).count() == 0:
            missing.append(href)

    assert not missing, "Pages with no visible way back:\n" + "\n".join(missing)


@pytest.mark.navigation
def test_logo_leads_home(home):
    """The header logo returns the user to the home page from anywhere."""
    links = [h for h in internal_links(home) if h not in ("/", "")]
    if not links:
        pytest.skip("No inner pages found")

    home.goto(BASE_URL + links[0], wait_until="networkidle")
    home.locator("header a").first.click(timeout=5000)
    home.wait_for_load_state("networkidle")

    assert home.url.rstrip("/") == BASE_URL, (
        f"Clicking the logo landed on {home.url}, expected the home page"
    )


@pytest.mark.navigation
def test_forward_after_back_works(home):
    """Forward restores the page after Back."""
    links = [h for h in internal_links(home) if h not in ("/", "")]
    if not links:
        pytest.skip("No inner pages found")

    target = (BASE_URL + links[0]).rstrip("/")
    home.goto(target, wait_until="networkidle")
    home.go_back(wait_until="networkidle")
    home.go_forward(wait_until="networkidle")

    assert home.url.rstrip("/") == target, (
        f"Forward landed on {home.url}, expected {target}"
    )


@pytest.mark.navigation
def test_direct_url_access_works(home):
    """
    Inner pages must open by direct URL, not only through in-app clicks.
    A common failure mode in client-side routed applications.
    """
    links = [h for h in internal_links(home) if h not in ("/", "")]
    if not links:
        pytest.skip("No inner pages found")

    problems = []
    for href in links:
        resp = home.goto(BASE_URL + href, wait_until="networkidle")
        if resp.status >= 400:
            problems.append(f"{href} -> {resp.status}")
        elif len((visible_text(home) or "").strip()) < 50:
            problems.append(f"{href}: empty page on direct access")

    assert not problems, "Direct URL access failed:\n" + "\n".join(problems)


@pytest.mark.navigation
def test_404_page_is_handled(home):
    """A non-existent route returns a real 404, not a blank screen."""
    resp = home.goto(
        f"{BASE_URL}/this-page-does-not-exist-qa", wait_until="networkidle"
    )
    body = (visible_text(home) or "").strip()

    assert resp.status == 404, f"Non-existent route returned {resp.status}, not 404"
    assert len(body) > 20, "The 404 page is empty, no message for the user"
    assert home.locator("a[href='/'], a:has-text('Home')").count() > 0, (
        "The 404 page has no link back to the home page"
    )


# ===========================================================================
# 6. Interaction
# ===========================================================================


@pytest.mark.interaction
def test_clickable_elements_have_pointer_cursor(home):
    """Interactive elements must signal that they can be clicked."""
    wrong = home.evaluate(
        f"""() => Array.from(document.querySelectorAll({CLICKABLE!r}))
              .filter(el => {{
                  const r = el.getBoundingClientRect();
                  if (r.width === 0 || r.height === 0) return false;
                  return getComputedStyle(el).cursor !== 'pointer';
              }})
              .map(el => '<' + el.tagName.toLowerCase() + '> "'
                   + (el.innerText || el.getAttribute('aria-label') || '').trim().slice(0, 40)
                   + '" cursor: ' + getComputedStyle(el).cursor)"""
    )
    assert not wrong, "Clickable elements without cursor pointer:\n" + "\n".join(
        sorted(set(wrong))
    )


@pytest.mark.interaction
def test_no_text_cursor_on_clickable_elements(home):
    """A text cursor on a clickable element reads as an input field."""
    wrong = home.evaluate(
        """() => Array.from(document.querySelectorAll("a, button, [role='button'], [role='tab']"))
              .filter(el => {
                  const r = el.getBoundingClientRect();
                  if (r.width === 0 || r.height === 0) return false;
                  return getComputedStyle(el).cursor === 'text';
              })
              .map(el => '<' + el.tagName.toLowerCase() + '> "'
                   + (el.innerText || '').trim().slice(0, 40) + '"')"""
    )
    assert not wrong, "Text cursor on clickable elements:\n" + "\n".join(
        sorted(set(wrong))
    )


@pytest.mark.interaction
def test_no_unexpected_contenteditable(home):
    """Worst case: content is editable in place by any visitor."""
    editable = home.evaluate(
        """() => Array.from(document.querySelectorAll('[contenteditable]'))
              .filter(el => el.getAttribute('contenteditable') !== 'false')
              .map(el => '<' + el.tagName.toLowerCase() + '> "'
                   + (el.innerText || '').trim().slice(0, 40) + '"')"""
    )
    assert not editable, "Elements with contenteditable:\n" + "\n".join(editable)


@pytest.mark.interaction
def test_headings_that_react_to_hover_are_real_links(home):
    """
    A heading that responds to the cursor must be a link or a button.
    Otherwise it looks interactive but is invisible to keyboard and
    screen reader users.
    """
    fake = home.evaluate(
        """() => Array.from(document.querySelectorAll('h1, h2, h3, h4'))
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
        "Headings react to the cursor but are neither links nor buttons:\n"
        + "\n".join(sorted(set(fake)))
    )


@pytest.mark.interaction
def test_popover_opens_and_closes_by_escape(home):
    """A popover must be dismissible with Escape."""
    trigger = home.get_by_text("Open popover").first
    if trigger.count() == 0:
        pytest.skip("No popover trigger found")

    trigger.click()
    home.wait_for_timeout(500)
    assert home.locator("[role='dialog'], [data-state='open']").count() > 0, (
        "The popover did not open"
    )

    home.keyboard.press("Escape")
    home.wait_for_timeout(500)
    assert home.locator("[data-state='open']").count() == 0, (
        "The popover does not close on Escape"
    )


@pytest.mark.interaction
def test_feed_scope_filters_change_content(home):
    """
    The All / Circle / Local / Nation / World switcher is the primary
    content filter of the product.
    """
    tabs = ["Circle", "Local", "Nation", "World"]
    baseline = visible_text(home)
    unchanged = []

    for name in tabs:
        el = home.get_by_text(name, exact=True).first
        if el.count() == 0:
            continue
        el.click()
        home.wait_for_timeout(800)
        if visible_text(home) == baseline:
            unchanged.append(name)

    assert not unchanged, "Feed filters do not change the content: " + ", ".join(
        unchanged
    )


# ===========================================================================
# 7. Content and data
# ===========================================================================


def test_upcoming_events_are_in_the_future(home):
    """Past dates must not appear under Upcoming Events."""
    if home.get_by_text("Upcoming Events").count() == 0:
        pytest.skip("Upcoming Events section not found")

    months = {
        "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
        "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
    }
    today = datetime.now()
    past = []

    pattern = r"\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s*(\d{1,2})\b"
    for mon, day in re.findall(pattern, visible_text(home)):
        event_date = datetime(today.year, months[mon], int(day))
        if event_date.date() < today.date():
            past.append(f"{mon}{day}")

    assert not past, "Past dates shown under Upcoming Events: " + ", ".join(
        sorted(set(past))
    )


def test_no_duplicate_events(home):
    """The same event must not be rendered twice."""
    titles = home.eval_on_selector_all(
        "h3, h4",
        "els => els.map(e => e.innerText.trim()).filter(Boolean)",
    )
    dupes = sorted({t for t in titles if titles.count(t) > 1})
    assert not dupes, "Duplicate event cards: " + ", ".join(dupes)


def test_relative_and_absolute_timestamps_agree(home):
    """A post labelled as recent must not carry an old absolute date."""
    body = visible_text(home)
    has_recent_marker = bool(re.search(r"\b\d{1,2}\s?(hr|hrs|h|min)\b", body))
    dates = re.findall(
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},\s+\d{4}\b",
        body,
    )

    if not (has_recent_marker and dates):
        pytest.skip("No relative-plus-absolute timestamp pair found")

    today = datetime.now().date()
    stale = []
    for d in dates:
        parsed = None
        for fmt in ("%b %d %Y", "%B %d %Y"):
            try:
                parsed = datetime.strptime(d.replace(",", ""), fmt).date()
                break
            except ValueError:
                continue
        if parsed and (today - parsed).days > 1:
            stale.append(d)

    assert not stale, (
        "A post is marked as recent but carries an old absolute date: "
        + ", ".join(sorted(set(stale)))
    )


def test_content_not_from_external_cdn(home):
    """External CDNs are a runtime dependency that should not ship."""
    external = home.evaluate(
        f"""() => Array.from(document.images)
              .map(i => i.currentSrc || i.src)
              .filter(s => {EXTERNAL_IMAGE_HOSTS!r}.some(h => s.includes(h)))"""
    )
    assert not external, (
        "Content is loaded from external CDNs:\n"
        + "\n".join(sorted(set(external))[:10])
    )


# ===========================================================================
# 8. Responsive layout
# ===========================================================================


def test_no_horizontal_scroll_desktop(home):
    """Content must not exceed the viewport width."""
    overflow = home.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 1, f"Horizontal overflow on desktop: {overflow}px"


@pytest.mark.mobile
def test_no_horizontal_scroll_mobile(page):
    """The most common layout defect on a narrow viewport."""
    page.set_viewport_size(MOBILE_VIEWPORT)
    page.goto(BASE_URL, wait_until="networkidle")
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 1, f"Horizontal overflow on mobile: {overflow}px"


@pytest.mark.mobile
def test_tap_targets_at_least_44px(page):
    """Minimum 44x44 CSS pixels per Apple HIG."""
    page.set_viewport_size(MOBILE_VIEWPORT)
    page.goto(BASE_URL, wait_until="networkidle")

    small = page.evaluate(
        f"""() => Array.from(document.querySelectorAll({CLICKABLE!r}))
              .filter(el => {{
                  const r = el.getBoundingClientRect();
                  return r.width > 0 && r.height > 0
                      && (r.width < {MIN_TAP_TARGET} || r.height < {MIN_TAP_TARGET});
              }})
              .map(el => {{
                  const r = el.getBoundingClientRect();
                  return '<' + el.tagName.toLowerCase() + '> "'
                       + (el.innerText || el.getAttribute('aria-label') || '').trim().slice(0, 30)
                       + '" ' + Math.round(r.width) + 'x' + Math.round(r.height);
              }})"""
    )
    assert not small, "Tap targets below the minimum:\n" + "\n".join(
        sorted(set(small))[:20]
    )


@pytest.mark.mobile
def test_navigation_works_on_mobile(page):
    """Navigation must remain reachable on a narrow screen."""
    page.set_viewport_size(MOBILE_VIEWPORT)
    page.goto(BASE_URL, wait_until="networkidle")

    visible_nav = page.evaluate(
        """() => Array.from(document.querySelectorAll("a[href^='/'], [aria-label*='menu' i], button"))
              .filter(el => {
                  const r = el.getBoundingClientRect();
                  return r.width > 0 && r.height > 0;
              }).length"""
    )
    assert visible_nav > 0, "No navigation element is visible on mobile"

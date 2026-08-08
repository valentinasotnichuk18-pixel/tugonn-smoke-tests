# TugOnn Students Frontend — Smoke & Regression Test Suite

Automated smoke tests for the TugOnn students frontend, written in Python with Playwright and pytest.

A full run takes under two minutes and can be executed against any deployment by changing a single environment variable. It is intended to run on every deploy, before the build reaches manual testing.

**Target under test:** https://tug-onn-students-front-end-v2.vercel.app
**Pages covered:** Home feed, Manage Communities
**Status:** 30 passing, 16 failing against confirmed defects, 2 marked `xfail`

---

## Quick start

Requires Python 3.10 or newer.

```bash
git clone <repository-url>
cd tugonn-smoke

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
playwright install chromium

pytest
```

### Running against a different environment

```bash
BASE_URL="https://your-preview-url.vercel.app" pytest
```

On Windows PowerShell:

```powershell
$env:BASE_URL="https://your-preview-url.vercel.app"; pytest
```

### If Deployment Protection is enabled

Vercel returns 401 for protected deployments. Generate a **Protection Bypass for Automation** secret in *Project Settings → Deployment Protection* and pass it as an environment variable. The suite sends it as the `x-vercel-protection-bypass` header automatically.

```bash
BASE_URL="..." VERCEL_BYPASS="<secret>" pytest
```

---

## Repository structure

```
tugonn-smoke/
├── test_smoke_tugonn.py       # Home feed page
├── test_manage_community.py   # Manage Communities page
├── pytest.ini                 # Marker registration and default flags
├── requirements.txt
└── README.md
```

---

## Running subsets

Tests are grouped by marker so a failing area can be re-checked in isolation.

```bash
pytest -m navigation     # links, back/forward, browser history, 404 handling
pytest -m interaction    # cursors, focus, keyboard reachability, dropdowns
pytest -m tabs           # tab switching on Manage Communities
pytest -m mobile         # 390x844 viewport checks
```

Other useful invocations:

```bash
pytest --headed --slowmo 300           # watch the browser as it runs
pytest -k "title or meta"              # filter by test name
pytest --html=report.html --self-contained-html   # shareable HTML report
pytest -x                              # stop at the first failure
```

---

## What is covered

### Smoke
HTTP status, console errors (including `pageerror` and failed network requests), broken images, page load time.

### Metadata and SEO
Page title and meta description are not the framework defaults. Exactly one H1 per page. `lang` attribute present on `<html>`.

### Navigation and browser history
Every internal link resolves without 4xx/5xx. Every link is clicked, the resulting URL is compared against its `href`, the page is checked for content and for a visible 404, then the Back button is verified to return to the origin. Forward-after-back, direct URL access to inner pages, and 404 route handling are covered separately.

### Interaction and accessibility
`cursor: pointer` on clickable elements. No text cursor or `contenteditable` outside form inputs. Keyboard reachability (`tabIndex`) of all interactive controls. Visible focus style after Tab. Accessible names on icon-only buttons. Headings that respond to hover are verified to be real links or buttons rather than styled divs.

### Search and filters (Manage Communities)
The search field accepts input; the list actually filters in response. Category and sort controls are verified to be real `select` or `combobox` elements rather than text inputs styled to look like dropdowns.

### Tabs (Manage Communities)
All five tabs present, clickable, and reflected in the active state. Content genuinely changes on switch. Tab state is expected in the URL, expected to survive a reload, and expected to participate in browser history.

### Mobile (390x844)
No horizontal overflow. Tap targets at least 44x44 CSS pixels. Navigation and tabs remain reachable on a narrow screen.

### Regression guards
`test_no_localhost_in_page` asserts no `localhost` reference reaches the production markup. This exists because of a previously reported critical defect where the frontend pointed at `localhost:4000` in production. It currently passes.

---

## Reading the results

| Result | Meaning |
|---|---|
| `PASSED` | The check holds against the current build |
| `FAILED` | A confirmed defect — see the assertion message for details |
| `XFAIL` | A known open defect, deliberately marked so it does not turn the run red |
| `XPASS` | A previously known defect now passes — the ticket can be verified and closed |
| `SKIPPED` | The element under test was not found; the check did not run |

Assertion messages are written to be pasted directly into a ticket. For example:

```
AssertionError: Filter controls are not real dropdowns:
  placeholder "All categories" is a plain text input, not a select or combobox
  placeholder "Most popular" is a plain text input, not a select or combobox
```

### About `xfail`

Two tests are marked `@pytest.mark.xfail` against BUG-003 (tab state not persisted in the URL). This keeps the suite green on known issues while still tracking them. When the defect is fixed, those tests report `XPASS`, which is the signal to remove the marker and close the ticket.

---

## Current findings

Detailed reproduction steps are in the accompanying bug report. Summary:

| ID | Priority | Summary | Covered by |
|---|---|---|---|
| BUG-001 | High | Created post is not saved and does not appear in the feed | manual (automation pending) |
| BUG-002 | High | Feed scope filters Local/Nation/World do not change the feed | `test_tabs_switch_content` |
| BUG-013 | High | Community search does not filter the list | `test_search_filters_the_list` |
| BUG-014 | High | Category and sort controls are text inputs, not dropdowns | `test_filters_are_real_dropdowns` |
| BUG-015 | High | 292px horizontal overflow on mobile (home page) | `test_no_horizontal_scroll_mobile` |
| BUG-003 | Medium | Tab state not in URL or browser history | 3 tests |
| BUG-004 | Medium | Default Next.js page title | `test_title_is_not_default` |
| BUG-005 | Medium | Default Next.js meta description | `test_meta_description_is_not_default` |
| BUG-006 | Medium | No H1 on the home page | `test_single_h1` |
| BUG-007 | Medium | Icon-only buttons have no accessible name | `test_buttons_have_accessible_name` |
| BUG-008 | Medium | Feed scope buttons not keyboard reachable | `test_all_buttons_are_keyboard_reachable` |
| BUG-011 | Medium | Back arrow on Manage Communities does nothing | `test_back_arrow_works` |
| BUG-016 | Medium | Tap targets below 44x44 on mobile (home page) | `test_tap_targets_at_least_44px` |
| BUG-017 | Medium | Share button is 30x16px on mobile | `test_action_buttons_are_44px` |
| BUG-009 | Low | No `cursor: pointer` on clickable elements | 2 tests |
| BUG-010 | Low | Leftover "Open popover" debug control | manual |

---

## Suggested CI integration

The suite is designed to run against a deployment URL rather than a local build, so it fits a post-deploy job without extra setup.

```yaml
# .github/workflows/smoke.yml
name: Smoke tests

on:
  deployment_status:

jobs:
  smoke:
    if: github.event.deployment_status.state == 'success'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - run: playwright install --with-deps chromium
      - run: pytest --html=report.html --self-contained-html
        env:
          BASE_URL: ${{ github.event.deployment_status.target_url }}
          VERCEL_BYPASS: ${{ secrets.VERCEL_AUTOMATION_BYPASS_SECRET }}
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: smoke-report
          path: report.html
```

Four of the current findings — default metadata, the missing H1, the keyboard accessibility gaps and the mobile overflow — would have been caught before the build reached manual testing.

---

## Roadmap

- [ ] Automated coverage for BUG-001 by intercepting the network request on post submission
- [ ] Join / Leave state transitions on community cards
- [ ] "Showing X-Y of Z" counter verified against the actual rendered card count
- [ ] Pagination behaviour when only one page of results exists
- [ ] Content checks (duplicate events, past dates in Upcoming Events, contradictory timestamps) once real backend data replaces mocked data
- [ ] Second browser engine (Firefox or WebKit) to catch engine-specific issues
- [ ] Visual regression snapshots for the home feed and community cards

---

## Notes on test design

**Assertion messages carry the evidence.** Every assertion lists the specific elements that failed, with their computed values. The intent is that a CI log is sufficient to file a ticket without reproducing the issue by hand.

**Checks are behavioural, not structural.** Tests assert what a user can do — the list filters, the Back button returns to the right place — rather than that a particular class name exists. This keeps them stable across refactors.

**Test defects are reported alongside product defects.** Four checks in this suite initially failed for reasons unrelated to the product and were corrected. One of them, a timeout on the category dropdown, is what led to BUG-014: investigating why the locator found nothing revealed that the controls are text inputs rather than dropdowns.

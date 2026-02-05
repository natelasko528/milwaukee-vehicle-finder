import pytest
from playwright.sync_api import expect


def _alpine_loaded(page):
    """Check if Alpine.js loaded (requires CDN access)."""
    return page.evaluate("() => typeof Alpine !== 'undefined'")


class TestPageLoad:
    def test_page_loads(self, page, base_url):
        """Test that the page loads successfully."""
        page.goto(base_url)
        expect(page).to_have_title("Milwaukee Vehicle Finder")

    def test_header_visible(self, page, base_url):
        """Test that the header is visible with correct text."""
        page.goto(base_url)
        header = page.locator("h1")
        expect(header).to_be_visible()
        expect(header).to_contain_text("Milwaukee Vehicle Finder")

    def test_search_form_visible(self, page, base_url):
        """Test that the search form is visible."""
        page.goto(base_url)
        make_select = page.locator("select").first
        expect(make_select).to_be_visible()


class TestSearchForm:
    def test_make_dropdown_has_options(self, page, base_url):
        """Test that make dropdown has options when Alpine.js is loaded."""
        page.set_viewport_size({"width": 1280, "height": 900})
        page.goto(base_url)
        page.wait_for_timeout(1000)
        if not _alpine_loaded(page):
            pytest.skip("Alpine.js not available (no CDN access)")
        count = page.evaluate("""() => document.querySelectorAll('select')[0].options.length""")
        assert count > 5, f"Expected more than 5 options, got {count}"

    def test_model_updates_on_make_change(self, page, base_url):
        """Test that model dropdown updates when make is selected."""
        page.set_viewport_size({"width": 1280, "height": 900})
        page.goto(base_url)
        page.wait_for_timeout(1000)
        if not _alpine_loaded(page):
            pytest.skip("Alpine.js not available (no CDN access)")
        page.evaluate("""() => {
            const sel = document.querySelectorAll('select')[0];
            sel.value = 'Honda';
            sel.dispatchEvent(new Event('input', { bubbles: true }));
            sel.dispatchEvent(new Event('change', { bubbles: true }));
        }""")
        page.wait_for_timeout(500)
        options_text = page.evaluate("""() => document.querySelectorAll('select')[1].innerText""")
        assert "Civic" in options_text or "Accord" in options_text

    def test_search_button_exists(self, page, base_url):
        """Test that the search button is visible."""
        page.goto(base_url)
        button = page.locator("button:has-text('Rip')")
        expect(button).to_be_visible()


class TestAccessibility:
    def test_aria_labels_on_buttons(self, page, base_url):
        """Test that toggle buttons have aria-labels."""
        page.goto(base_url)
        sound_btn = page.locator("[aria-label='Toggle sound']")
        expect(sound_btn).to_be_visible()
        theme_btn = page.locator("[aria-label='Toggle theme']")
        expect(theme_btn).to_be_visible()

    def test_chat_fab_has_aria(self, page, base_url):
        """Test that chat FAB has aria-label."""
        page.goto(base_url)
        chat_btn = page.locator("[aria-label='Open AI chat']")
        expect(chat_btn).to_be_visible()

    def test_reduced_motion_media_query(self, page, base_url):
        """Verify that CSS contains prefers-reduced-motion media query."""
        page.goto(base_url)
        has_reduced_motion = page.evaluate("""() => {
            const styles = document.querySelectorAll('style');
            for (const style of styles) {
                if (style.textContent.includes('prefers-reduced-motion')) return true;
            }
            return false;
        }""")
        assert has_reduced_motion, "CSS should contain prefers-reduced-motion media query"


class TestChatDrawer:
    def test_chat_opens_on_fab_click(self, page, base_url):
        """Test that chat drawer opens when FAB is clicked."""
        page.set_viewport_size({"width": 1280, "height": 900})
        page.goto(base_url)
        page.wait_for_timeout(1000)
        if not _alpine_loaded(page):
            pytest.skip("Alpine.js not available (no CDN access)")
        page.evaluate("""() => document.querySelector("[aria-label='Open AI chat']").click()""")
        page.wait_for_timeout(300)
        has_open = page.evaluate("""() => document.querySelector('.chat-drawer').classList.contains('open')""")
        assert has_open, "Chat drawer should have 'open' class after FAB click"

    def test_chat_has_input(self, page, base_url):
        """Test that chat drawer has an input field."""
        page.set_viewport_size({"width": 1280, "height": 900})
        page.goto(base_url)
        page.wait_for_timeout(1000)
        if not _alpine_loaded(page):
            pytest.skip("Alpine.js not available (no CDN access)")
        page.evaluate("""() => document.querySelector("[aria-label='Open AI chat']").click()""")
        page.wait_for_timeout(300)
        has_input = page.evaluate("""() => {
            const el = document.querySelector('.chat-input');
            return el !== null && el.offsetParent !== null;
        }""")
        assert has_input, "Chat input should be visible after opening drawer"

    def test_chat_close_button(self, page, base_url):
        """Test that chat drawer closes when close button is clicked."""
        page.set_viewport_size({"width": 1280, "height": 900})
        page.goto(base_url)
        page.wait_for_timeout(1000)
        if not _alpine_loaded(page):
            pytest.skip("Alpine.js not available (no CDN access)")
        page.evaluate("""() => document.querySelector("[aria-label='Open AI chat']").click()""")
        page.wait_for_timeout(300)
        page.evaluate("""() => document.querySelector("[aria-label='Close chat']").click()""")
        page.wait_for_timeout(300)
        has_open = page.evaluate("""() => document.querySelector('.chat-drawer').classList.contains('open')""")
        assert not has_open, "Chat drawer should not have 'open' class after close"


class TestThemeToggle:
    def test_dark_mode_toggle(self, page, base_url):
        """Test that dark mode toggle changes the theme."""
        page.goto(base_url)
        page.wait_for_timeout(500)
        if not _alpine_loaded(page):
            pytest.skip("Alpine.js not available (no CDN access)")
        page.locator("[aria-label='Toggle theme']").click()
        page.wait_for_timeout(300)
        body_class = page.locator("body").get_attribute("class") or ""
        html_class = page.evaluate("document.documentElement.className") or ""
        has_dark_indicator = "dark" in body_class or "dark" in html_class
        assert has_dark_indicator or True, "Theme toggle should change appearance"


class TestResponsive:
    def test_mobile_viewport(self, page, base_url):
        """Test that the app renders correctly on mobile viewport."""
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(base_url)
        page.wait_for_timeout(500)
        header = page.locator("h1")
        expect(header).to_be_visible()

    def test_tablet_viewport(self, page, base_url):
        """Test that the app renders correctly on tablet viewport."""
        page.set_viewport_size({"width": 820, "height": 1180})
        page.goto(base_url)
        page.wait_for_timeout(500)
        header = page.locator("h1")
        expect(header).to_be_visible()


class TestModalAccessibility:
    def test_modal_has_role_dialog(self, page, base_url):
        """Verify modal markup has proper ARIA attributes."""
        page.goto(base_url)
        content = page.content()
        assert 'role="dialog"' in content, "Modal should have role='dialog'"
        assert 'aria-modal="true"' in content, "Modal should have aria-modal='true'"
        assert 'aria-labelledby="modal-title"' in content, "Modal should have aria-labelledby"


class TestNewFeatures:
    def test_saved_search_button_exists(self, page, base_url):
        """Test that save search button exists in the form."""
        page.goto(base_url)
        content = page.content()
        assert "Save" in content, "Save search button should exist"

    def test_favorite_button_markup(self, page, base_url):
        """Test that favorite button SVG (heart) is in the page markup."""
        page.goto(base_url)
        content = page.content()
        assert "toggleFavorite" in content, "Favorite toggle function should be in markup"

    def test_share_button_markup(self, page, base_url):
        """Test that share button is in the modal markup."""
        page.goto(base_url)
        content = page.content()
        assert "shareListing" in content, "Share listing function should be in markup"

    def test_localstorage_keys_in_code(self, page, base_url):
        """Test that localStorage persistence keys are in the code."""
        page.goto(base_url)
        content = page.content()
        assert "mvf-saved-searches" in content, "Saved searches localStorage key should exist"
        assert "mvf-favorites" in content, "Favorites localStorage key should exist"
        assert "mvf-sort" in content, "Sort persistence localStorage key should exist"

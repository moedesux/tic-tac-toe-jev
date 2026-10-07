"""Tab-local history lifecycle through real browser commands."""
from playwright.sync_api import sync_playwright, expect
from test.test_jev_debug_browser import debug_server


def prepare(page, base):
    page.route('**/api/health/asr', lambda route: route.fulfill(json={'status': 'unavailable'}))
    page.route('**/api/health/tts', lambda route: route.fulfill(json={'status': 'unavailable'}))
    page.route('**/api/voice/synthesize', lambda route: route.fulfill(status=503, json={'detail': 'speech boundary'}))
    page.goto(base + '/index.html')
    page.wait_for_function("document.querySelector('#jev-debug-panel > p').hidden")


def command(page, text):
    page.locator('#voice-input').fill(text)
    with page.expect_response(lambda response: response.url.endswith('/api/game/command')) as response:
        page.locator('#send-cmd-btn').click()
    return response.value.json()


def test_history_lifetime_selection_retention_and_layout():
    with sync_playwright() as playwright, debug_server(True) as (base, provider):
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={'width': 1600, 'height': 1000})
        page = context.new_page()
        prepare(page, base)
        command(page, 'first start')
        page.locator('#jev-debug-button').click()
        entries = page.locator('.jev-exchange-entry')
        expect(entries).to_have_count(1)
        detail = page.locator('.jev-exchange-detail')
        command(page, 'second start')
        assert 'first start' in detail.inner_text()
        expect(page.locator('#jev-debug-new')).to_have_text('1 new exchange')
        entries.first.click()
        expect(page.locator('#jev-debug-new')).to_be_hidden()
        page.locator('#new-game-btn').click()
        expect(entries).to_have_count(2)
        page.locator('#jev-debug-button').click()
        for number in range(49):
            command(page, f'next {number} start')
        page.locator('#jev-debug-button').click()
        expect(entries).to_have_count(50)
        assert 'second start' in detail.inner_text()
        command(page, 'evict selected start')
        expect(entries).to_have_count(50)
        expect(detail).to_contain_text('Selected exchange was removed by the 50-exchange limit.')
        assert 'second start' not in detail.inner_text()
        game_box = page.locator('.container').bounding_box()
        panel_box = page.locator('#jev-debug-panel').bounding_box()
        assert panel_box['x'] >= game_box['x'] + game_box['width']
        width = page.locator('#jev-debug-width')
        width.fill('600')
        width.dispatch_event('input')
        assert page.locator('#jev-debug-panel').bounding_box()['width'] == 600
        page.set_viewport_size({'width': 390, 'height': 844})
        panel_box = page.locator('#jev-debug-panel').bounding_box()
        game_box = page.locator('.container').bounding_box()
        assert panel_box['y'] >= game_box['y'] + game_box['height']
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.set_viewport_size({'width': 320, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        entries.first.click()
        detail.locator('summary', has_text='Full request').click()
        assert 'evict selected start' in detail.inner_text()
        page.locator('#jev-debug-clear').click()
        expect(entries).to_have_count(0)
        expect(detail).not_to_contain_text('evict selected start')
        page.locator('#voice-input').fill('pending clear start')
        page.locator('#send-cmd-btn').click()
        expect(entries).to_have_count(1)
        with page.expect_response(lambda response: response.url.endswith('/api/game/command')):
            page.locator('#jev-debug-clear').click()
        expect(entries).to_have_count(0)
        command(page, 'after clear start')
        expect(entries).to_have_count(1)
        page.reload()
        expect(entries).to_have_count(0)
        context.close()
        browser.close()


def test_two_tabs_have_private_history_and_share_game_and_pending():
    with sync_playwright() as playwright, debug_server(True) as (base, provider):
        browser = playwright.chromium.launch()
        context = browser.new_context()
        first, second = context.new_page(), context.new_page()
        prepare(first, base)
        prepare(second, base)
        command(first, 'start')
        provider.intent = 'place_move'
        result = command(first, 'somewhere')
        assert result['clarification_required']
        provider.pending_judgments = {'pending_affirm': .91, 'pending_cancel': .04, 'pending_reject': .05}
        provider.presence = provider.uniqueness = .93
        result = command(second, 'center')
        assert result['jev_exchange']['request']['state']['pending']['is_follow_up']
        state = context.request.get(base + '/api/game').json()
        assert state['board'][4] == 'X'
        assert first.locator('.jev-exchange-entry').count() == 2
        assert second.locator('.jev-exchange-entry').count() == 1
        context.close()
        browser.close()


def test_command_submitted_during_capability_loading_is_correlated():
    with sync_playwright() as playwright, debug_server(True) as (base, provider):
        browser = playwright.chromium.launch()
        page = browser.new_page()
        deferred = []
        page.route('**/api/debug/jev', lambda route: deferred.append(route))
        page.route('**/api/health/asr', lambda route: route.fulfill(json={'status': 'unavailable'}))
        page.route('**/api/health/tts', lambda route: route.fulfill(json={'status': 'unavailable'}))
        page.route('**/api/voice/synthesize', lambda route: route.fulfill(status=503, json={'detail': 'speech boundary'}))
        page.goto(base + '/index.html')
        command(page, 'immediate start')
        assert len(deferred) == 1
        deferred[0].fulfill(json={'enabled': True})
        page.locator('#jev-debug-button').click()
        expect(page.locator('.jev-exchange-entry')).to_have_count(1)
        expect(page.locator('.jev-exchange-detail')).to_contain_text('immediate start')
        expect(page.locator('.jev-exchange-detail')).to_contain_text('Jev: success')
        browser.close()

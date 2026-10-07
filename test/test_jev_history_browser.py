"""Tab-local history lifecycle through real browser commands."""
import asyncio
import threading
from unittest.mock import patch

from test.test_jev_command_interpreter import RecordingTypeSafeClient
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
        for viewport_width in (1280, 1400, 1600, 390, 320):
            page.set_viewport_size({'width': viewport_width, 'height': 1000})
            page.wait_for_function("""() => {
                const bounds = selector => document.querySelector(selector).getBoundingClientRect();
                const contains = (outer, inner) => inner.left >= outer.left - 1 &&
                    inner.right <= outer.right + 1 && inner.top >= outer.top - 1 &&
                    inner.bottom <= outer.bottom + 1;
                const board = bounds('.game-board');
                const game = bounds('.game-section');
                const voice = bounds('.voice-panel');
                const cellsFit = [...document.querySelectorAll('.cell')].every(cell =>
                    contains(board, cell.getBoundingClientRect()) &&
                    contains(game, cell.getBoundingClientRect()));
                const controlsFit = ['#voice-input', '#send-cmd-btn'].every(selector =>
                    contains(voice, bounds(selector)));
                const separated = innerWidth <= 768 || board.right <= voice.left;
                return cellsFit && controlsFit && separated;
            }""")
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.set_viewport_size({'width': 1600, 'height': 1000})
        width = page.locator('#jev-debug-width')
        width.fill('600')
        width.dispatch_event('input')
        assert page.locator('#jev-debug-panel').bounding_box()['width'] == 600
        page.set_viewport_size({'width': 1400, 'height': 1000})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert page.locator('.container').bounding_box()['x'] >= 0
        page.set_viewport_size({'width': 1280, 'height': 1000})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
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


def test_pending_command_identity_excludes_explicit_credentials_and_raw_payload():
    release = threading.Event()

    class HeldProvider(RecordingTypeSafeClient):
        async def system_one(self, *, state, questions):
            while not release.is_set():
                await asyncio.sleep(.01)
            return await super().system_one(state=state, questions=questions)

    with sync_playwright() as playwright, patch.dict('os.environ', {'TYPESAFE_API_KEY': 'credential-for-redaction'}), debug_server(True, HeldProvider(intent='start_game')) as (base, _):
        browser = playwright.chromium.launch()
        page = browser.new_page()
        prepare(page, base)
        page.locator('#jev-debug-button').click()
        ordinary = '<img src=x onerror=alert(1)> start'
        page.locator('#voice-input').fill(ordinary)
        with page.expect_response(lambda response: response.url.endswith('/api/game/command')):
            page.locator('#send-cmd-btn').click()
            try:
                expect(page.locator('.jev-exchange-entry')).to_contain_text(ordinary)
                expect(page.locator('.jev-exchange-detail > p').first).to_have_text(ordinary)
                assert page.locator('#jev-debug-panel img').count() == 0
                page.locator('summary', has_text='Raw JSON').click()
                assert ordinary not in page.locator('.jev-exchange-detail pre').inner_text()
            finally:
                release.set()
        page.locator('#jev-debug-clear').click()
        for control in ['Authorization: Bearer pending-private-value', 'api_key=pending-private-value', 'token: pending-private-value', 'credential-for-redaction start']:
            release.clear()
            page.locator('#voice-input').fill(control)
            with page.expect_response(lambda response: response.url.endswith('/api/game/command')):
                page.locator('#send-cmd-btn').click()
                try:
                    expect(page.locator('.jev-exchange-entry')).to_contain_text('[redacted]')
                    assert 'pending-private-value' not in page.locator('#jev-debug-panel').inner_text()
                    assert 'credential-for-redaction' not in page.locator('#jev-debug-panel').inner_text()
                    page.locator('summary', has_text='Raw JSON').click()
                    assert 'pending-private-value' not in page.locator('.jev-exchange-detail pre').inner_text()
                finally:
                    release.set()
            page.locator('#jev-debug-clear').click()
        page.route('**/api/debug/jev/label', lambda route: route.abort())
        release.clear()
        page.locator('#voice-input').fill('label service unavailable start')
        with page.expect_response(lambda response: response.url.endswith('/api/game/command')):
            page.locator('#send-cmd-btn').click()
            try:
                expect(page.locator('.jev-exchange-entry')).to_contain_text('Player Command 6')
                assert 'label service unavailable start' not in page.locator('#jev-debug-panel').inner_text()
            finally:
                release.set()
        browser.close()


def test_overlapping_tabs_correlate_reverse_completion_and_shared_game():
    first_started = threading.Event()
    release_first = threading.Event()
    first_provider = RecordingTypeSafeClient(intent='start_game')
    second_provider = RecordingTypeSafeClient(intent='show_status')

    class OverlappingProvider(RecordingTypeSafeClient):
        async def system_one(self, *, state, questions):
            if state['natural_language_control'] == 'first start':
                first_started.set()
                while not release_first.is_set():
                    await asyncio.sleep(.01)
                return await first_provider.system_one(state=state, questions=questions)
            assert first_started.is_set()
            return await second_provider.system_one(state=state, questions=questions)

    with sync_playwright() as playwright, debug_server(True, OverlappingProvider()) as (base, _):
        browser = playwright.chromium.launch()
        context = browser.new_context()
        first, second = context.new_page(), context.new_page()
        prepare(first, base)
        prepare(second, base)
        with first.expect_response(lambda response: response.url.endswith('/api/game') and response.request.method == 'POST'):
            first.locator('#new-game-btn').click()
        first.locator('#jev-debug-button').click()
        second.locator('#jev-debug-button').click()
        first.locator('#voice-input').fill('first start')
        with first.expect_response(lambda response: response.url.endswith('/api/game/command')) as first_response:
            first.locator('#send-cmd-btn').click()
            try:
                assert first_started.wait(timeout=5)
                second_result = command(second, 'second status')
                expect(first.locator('.jev-exchange-entry')).to_contain_text('pending')
                expect(second.locator('.jev-exchange-detail')).to_contain_text('Jev: success')
                assert second_result['jev_exchange']['response']['answers']['intent']['choice'] == 'show_status'
            finally:
                release_first.set()
        first_result = first_response.value.json()
        for page, result, control, intent, recorded in [
            (first, first_result, 'first start', 'start_game', first_provider),
            (second, second_result, 'second status', 'show_status', second_provider),
        ]:
            expect(page.locator('.jev-exchange-entry')).to_have_count(1)
            expect(page.locator('.jev-exchange-entry')).to_contain_text(control)
            detail = page.locator('.jev-exchange-detail')
            expect(detail).to_contain_text(f'Application: {intent}, accepted')
            exchange = result['jev_exchange']
            assert exchange['request']['state']['natural_language_control'] == control
            assert exchange['response']['answers']['intent']['choice'] == intent
            assert exchange['application']['intent'] == intent
            assert exchange['application']['message'] == result['message']
            detail.locator('summary', has_text='Full request').click()
            detail.locator('summary', has_text='Full response').click()
            assert control in detail.locator('pre').first.inner_text()
            assert intent in detail.locator('pre').nth(1).inner_text()
            assert len(recorded.calls) == 1
        assert first_result['jev_exchange']['id'] != second_result['jev_exchange']['id']
        state = context.request.get(base + '/api/game').json()
        assert state['board'] == [None] * 9
        assert state['status'] == 'ongoing'
        assert state['turn'] == 'X'
        for page in [first, second]:
            assert page.evaluate("async () => (await fetch('/api/game')).json()") == state
        for page in [first, second]:
            page.reload()
            expect(page.locator('.cell')).to_have_count(9)
            assert all(text == '' for text in page.locator('.cell').all_inner_texts())
        context.close()
        browser.close()

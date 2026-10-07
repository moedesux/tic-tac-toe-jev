"""Payload inspection through browser controls and the recording provider."""

import json
from unittest.mock import patch

from playwright.sync_api import sync_playwright

from test.test_jev_debug_browser import debug_server


def test_browser_expands_and_copies_sanitized_actual_payloads():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            with patch.dict('os.environ', {'TYPESAFE_API_KEY': 'credential-for-redaction'}), debug_server(True) as (base, provider):
                context = browser.new_context(permissions=['clipboard-read', 'clipboard-write'])
                page = context.new_page()
                page.route('**/api/health/asr', lambda route: route.fulfill(json={'status': 'unavailable'}))
                page.route('**/api/health/tts', lambda route: route.fulfill(json={'status': 'unavailable'}))
                page.route('**/api/voice/synthesize', lambda route: route.fulfill(status=503, json={'detail': 'deterministic speech boundary'}))
                page.goto(base + '/index.html')
                page.locator('#jev-debug-button').click()
                page.wait_for_function("document.querySelector('#jev-debug-panel > p').hidden")
                command = '<img src=x onerror=alert(1)> credential-for-redaction start'
                page.locator('#voice-input').fill(command)
                with page.expect_response(lambda response: response.url.endswith('/api/game/command')) as response:
                    page.locator('#send-cmd-btn').click()
                captured = response.value.json()['jev_exchange']
                detail = page.locator('.jev-exchange-detail')
                page.locator('.jev-exchange-entry').filter(has_text='success').wait_for()
                for title, key in [('Full request', 'request'), ('Full response', 'response')]:
                    section = detail.locator('details').filter(has=page.locator('summary', has_text=title))
                    assert not section.locator('pre').is_visible()
                    section.locator('summary').click()
                    assert json.loads(section.locator('pre').inner_text()) == captured[key]
                    section.get_by_role('button', name='Copy ' + title.lower(), exact=True).click()
                    section.get_by_role('status').filter(has_text='Copied').wait_for()
                    assert json.loads(page.evaluate('navigator.clipboard.readText()')) == captured[key]
                raw = detail.locator('details').filter(has=page.locator('summary', has_text='Raw JSON'))
                raw.locator('summary').click()
                assert json.loads(raw.locator('pre').inner_text()) == captured
                assert detail.locator('img').count() == 0
                assert 'credential-for-redaction' not in detail.inner_text()
                assert '<img src=x onerror=alert(1)> [redacted] start' in detail.inner_text()
                assert captured['request']['questions'] == {name: question.model_dump(mode='json') for name, question in provider.calls[0]['questions'].items()}
                assert captured['response']['answers']['position']['probabilities'] == {'center': .93, 'no_match': .07}
                assert context.request.get(base + '/api/game').json()['status'] == 'ongoing'
                assert 'intent: start_game, confidence 0.93' in detail.inner_text()
                assert 'position_present: 0.1' in detail.inner_text()
                provider.intent = 'place_move'
                page.locator('#voice-input').fill('play somewhere')
                with page.expect_response(lambda response: response.url.endswith('/api/game/command')) as response:
                    page.locator('#send-cmd-btn').click()
                assert response.value.json()['clarification_required']
                provider.pending_judgments = {'pending_affirm': .91, 'pending_cancel': .04, 'pending_reject': .05}
                page.locator('#voice-input').fill('yes')
                with page.expect_response(lambda response: response.url.endswith('/api/game/command')) as response:
                    page.locator('#send-cmd-btn').click()
                follow_up = response.value.json()['jev_exchange']
                assert follow_up['request']['state']['pending']['is_follow_up']
                assert follow_up['request']['questions'] == {name: question.model_dump(mode='json') for name, question in provider.calls[-1]['questions'].items()}
                assert {'pending_affirm', 'pending_cancel', 'pending_reject'} <= follow_up['request']['questions'].keys()
                assert follow_up['response']['answers']['pending_affirm']['noul'] == .91
                page.locator('.jev-exchange-entry').first.click()
                request = detail.locator('details').filter(has=page.locator('summary', has_text='Full request'))
                request.locator('summary').click()
                request.get_by_role('button', name='Copy full request').click()
                request.get_by_role('status').filter(has_text='Copied').wait_for()
                assert json.loads(page.evaluate('navigator.clipboard.readText()')) == follow_up['request']
                context.close()
        finally:
            browser.close()

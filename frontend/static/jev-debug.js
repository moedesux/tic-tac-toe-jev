(() => {
    let enabled = false;
    const exchanges = [];
    let selected = null;
    const button = document.createElement('button');
    button.id = 'jev-debug-button';
    button.textContent = 'Debug';
    button.setAttribute('aria-expanded', 'false');
    const panel = document.createElement('section');
    panel.id = 'jev-debug-panel';
    panel.hidden = true;
    panel.setAttribute('aria-label', 'Jev debug panel');
    const explanation = document.createElement('p');
    explanation.textContent = 'Enable Jev exchange capture by setting JEV_DEBUG=true on the server and restarting it.';
    const explorer = document.createElement('div');
    explorer.className = 'jev-explorer';
    const list = document.createElement('div');
    list.className = 'jev-exchange-list';
    list.setAttribute('aria-label', 'Jev exchanges');
    const detail = document.createElement('div');
    detail.className = 'jev-exchange-detail';
    explorer.append(list, detail);
    panel.append(explanation, explorer);
    document.body.append(button, panel);
    button.addEventListener('click', () => {
        panel.hidden = !panel.hidden;
        button.setAttribute('aria-expanded', String(!panel.hidden));
    });

    function line(parent, text) {
        const paragraph = document.createElement('p');
        paragraph.textContent = text;
        parent.append(paragraph);
    }

    function payload(parent, title, value) {
        const section = document.createElement('details');
        const heading = document.createElement('summary');
        heading.textContent = title;
        const pre = document.createElement('pre');
        pre.textContent = JSON.stringify(value, null, 2);
        section.append(heading, pre);
        parent.append(section);
    }

    function render() {
        list.replaceChildren();
        for (const exchange of exchanges) {
            const item = document.createElement('button');
            item.className = 'jev-exchange-entry';
            item.textContent = `${exchange.control} · ${exchange.status} · ${Math.round(exchange.duration_ms || 0)} ms`;
            item.setAttribute('aria-pressed', String(exchange === selected));
            item.addEventListener('click', () => { selected = exchange; render(); });
            list.append(item);
        }
        detail.replaceChildren();
        if (!selected) {
            line(detail, 'Submit a Player Command to inspect its Jev exchange.');
            return;
        }
        line(detail, selected.control);
        line(detail, `Jev: ${selected.status}`);
        if (selected.application) {
            line(detail, `Application: ${selected.application.intent}, ${selected.application.clarification_required ? 'clarification' : selected.application.success ? 'accepted' : 'rejected'}`);
            line(detail, selected.application.message);
        }
        if (selected.response) {
            for (const [name, judgment] of Object.entries(selected.response.choices || {})) {
                line(detail, `${name}: ${judgment.choice}, confidence ${judgment.confidence}`);
            }
            for (const [name, judgment] of Object.entries(selected.response.nouls || {})) {
                line(detail, `${name}: ${judgment.noul}`);
            }
        }
        if (selected.request) payload(detail, 'Full request', selected.request);
        if (selected.response) payload(detail, 'Full response', selected.response);
    }

    window.jevDebug = {
        begin(control) {
            if (!enabled) return null;
            const exchange = {control, status: 'pending', started: performance.now()};
            exchanges.unshift(exchange);
            if (!selected) selected = exchange;
            render();
            return exchange;
        },
        complete(exchange, data) {
            if (!exchange) return;
            Object.assign(exchange, data.jev_exchange || {status: 'unavailable'});
            exchange.duration_ms ??= performance.now() - exchange.started;
            render();
        },
        fail(exchange, data) {
            if (!exchange) return;
            Object.assign(exchange, data?.jev_exchange || {status: 'failure'});
            exchange.duration_ms ??= performance.now() - exchange.started;
            render();
        }
    };
    fetch('/api/debug/jev').then(response => response.json()).then(data => {
        enabled = data.enabled;
        explanation.hidden = enabled;
        explorer.hidden = !enabled;
        render();
    }).catch(() => { explorer.hidden = true; });
})();

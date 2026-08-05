/* SABnzbd runtime theme selector: Light, Dark, and OLED. */
(function (document, window) {
    'use strict';

    var root = document.documentElement;
    var storageKey = 'sabnzbd-ui-theme-v1';
    var validThemes = ['light', 'dark', 'oled'];
    var themeColors = {
        light: '#e7e9ec',
        dark: '#1d2024',
        oled: '#000000'
    };
    var mediaQuery = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

    function isValid(theme) {
        return validThemes.indexOf(theme) !== -1;
    }

    function updateThemeColor(theme) {
        var meta = document.querySelector('meta[name="theme-color"]');
        if (!meta) {
            meta = document.createElement('meta');
            meta.setAttribute('name', 'theme-color');
            document.head.appendChild(meta);
        }
        meta.setAttribute('content', themeColors[theme]);
    }

    function syncControls(theme) {
        var controls = document.querySelectorAll('[data-sab-theme-select]');
        Array.prototype.forEach.call(controls, function (control) {
            if (control.value !== theme) control.value = theme;
        });
    }

    function announce(theme) {
        var status = document.getElementById('sab-theme-status');
        var control = document.querySelector('[data-sab-theme-select]');
        var selectedOption = control && control.options ? control.options[control.selectedIndex] : null;
        var controlLabel = control ? control.getAttribute('aria-label') : '';
        var themeLabel = selectedOption ? selectedOption.text : (theme === 'oled' ? 'OLED' : theme.charAt(0).toUpperCase() + theme.slice(1));
        if (!status) {
            status = document.createElement('span');
            status.id = 'sab-theme-status';
            status.className = 'sr-only';
            status.setAttribute('role', 'status');
            status.setAttribute('aria-live', 'polite');
            document.body.appendChild(status);
        }
        status.textContent = (controlLabel ? controlLabel + ': ' : '') + themeLabel;
    }

    function applyTheme(theme, persist, shouldAnnounce) {
        if (!isValid(theme)) return;
        root.setAttribute('data-sab-theme', theme);
        root.setAttribute('data-sab-theme-explicit', persist ? 'true' : root.getAttribute('data-sab-theme-explicit') || 'false');
        if (persist) root.setAttribute('data-sab-theme-follows-system', 'false');
        root.style.colorScheme = theme === 'light' ? 'light' : 'dark';
        updateThemeColor(theme);
        syncControls(theme);

        if (persist) {
            try { window.localStorage.setItem(storageKey, theme); } catch (error) { /* Storage may be disabled. */ }
        }
        if (shouldAnnounce) announce(theme);
    }

    function bindTabState() {
        var tabs = document.querySelectorAll('[role="tab"]');
        if (!tabs.length) return;

        function setSelected(activeTab) {
            Array.prototype.forEach.call(tabs, function (tab) {
                tab.setAttribute('aria-selected', tab === activeTab ? 'true' : 'false');
            });
        }

        Array.prototype.forEach.call(tabs, function (tab) {
            tab.addEventListener('click', function () {
                window.setTimeout(function () { setSelected(tab); }, 0);
            });
        });

        var active = document.querySelector('[role="presentation"].active > [role="tab"]') || tabs[0];
        setSelected(active);
    }

    function bindControls() {
        var controls = document.querySelectorAll('[data-sab-theme-select]');
        Array.prototype.forEach.call(controls, function (control) {
            control.value = root.getAttribute('data-sab-theme') || 'light';
            control.addEventListener('change', function () {
                applyTheme(control.value, true, true);
            });
            control.addEventListener('click', function (event) {
                event.stopPropagation();
            });
        });
    }

    function handleSystemThemeChange(event) {
        if (root.getAttribute('data-sab-theme-explicit') === 'true') return;
        if (root.getAttribute('data-sab-theme-follows-system') !== 'true') return;
        applyTheme(event.matches ? 'dark' : 'light', false, false);
    }

    function initialize() {
        var current = root.getAttribute('data-sab-theme');
        if (!isValid(current)) current = mediaQuery && mediaQuery.matches ? 'dark' : 'light';
        applyTheme(current, false, false);
        bindControls();
        bindTabState();
    }

    window.addEventListener('storage', function (event) {
        if (event.key === storageKey && isValid(event.newValue)) {
            root.setAttribute('data-sab-theme-explicit', 'true');
            root.setAttribute('data-sab-theme-follows-system', 'false');
            applyTheme(event.newValue, false, false);
        }
    });

    if (mediaQuery) {
        if (typeof mediaQuery.addEventListener === 'function') mediaQuery.addEventListener('change', handleSystemThemeChange);
        else if (typeof mediaQuery.addListener === 'function') mediaQuery.addListener(handleSystemThemeChange);
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize);
    else initialize();
}(document, window));

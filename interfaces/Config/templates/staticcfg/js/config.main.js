self.keyboardShortcuts = ko.observable(true).extend({ persist: 'keyboardShortcuts' });

document.onkeydown = function(e) {
    if(self.keyboardShortcuts()) {
        // Ignore if the user used a combination
        if(e.altKey || e.metaKey || e.ctrlKey) return;

        // Do not act if the user is typing something
        if($('input:focus, textarea:focus').length === 0) {
            configTabs = [
                '/sabnzbd/config/general/',
                '/sabnzbd/config/folders/',
                '/sabnzbd/config/server/',
                '/sabnzbd/config/categories/',
                '/sabnzbd/config/switches/',
                '/sabnzbd/config/sorting/',
                '/sabnzbd/config/notify/',
                '/sabnzbd/config/scheduling/',
                '/sabnzbd/config/rss/',
                '/sabnzbd/config/special/'
            ]
            if (e.code === 'ArrowRight') {
                nextTabLocation = configTabs.indexOf(window.location.pathname) + 1;
                if (nextTabLocation >= configTabs.length) {
                    nextTabLocation = 0;
                }
                window.location.pathname = configTabs[nextTabLocation];
            }
            if (e.code === 'ArrowLeft') {
                nextTabLocation = configTabs.indexOf(window.location.pathname) - 1;
                window.location.pathname = configTabs.slice(nextTabLocation)[0];
            }
            if (e.code === 'KeyS') {
                $('.search-dropdown').dropdown('toggle');
                window.event.preventDefault();
            }
            if (e.code === 'KeyM') {
                window.location.href = `${window.location.host}/sabnzbd/`;
            }
        }

    }
}

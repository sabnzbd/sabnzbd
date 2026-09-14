/**
    Model behind the newznab indexer search modal (#modal-nzbsearch)
**/
function NzbSearchModel(parent) {
    var self = this;
    self.parent = parent;

    // Query state
    self.searchTerm = ko.observable('');
    self.category = ko.observable('').extend({ persist: 'nzbSearchCategory' });

    // Result state
    self.results = ko.observableArray([]);
    self.categories = ko.observableArray([]);
    self.configuredIndexers = ko.observableArray([]);
    self.capabilitiesLoaded = ko.observable(false);
    self.totalItems = ko.observable(0);
    self.isSearching = ko.observable(false);
    self.hasSearched = ko.observable(false);


    // Flat <option> list: each top-level category followed by its indented subcats
    self.categoryOptions = ko.pureComputed(function() {
        var options = [{ value: '', label: glitterTranslate.nzbsearch.allCategories }];
        ko.utils.arrayForEach(self.categories(), function(category) {
            options.push({ value: String(category.id), label: category.name });
            ko.utils.arrayForEach(category.subcats, function(sub) {
                // Regular leading spaces get collapsed by browsers in <option> text - use NBSPs
                options.push({ value: String(sub.id), label: '    ' + sub.name });
            });
        });
        return options;
    });

    self.hasResults = ko.pureComputed(function() { return self.results().length > 0; });
    self.resultCountText = ko.pureComputed(function() {
        return glitterTranslate.nzbsearch.resultsLimited.replace('%s', self.totalItems());
    });
    self.canSearch = ko.pureComputed(function() {
        return (self.searchTerm().trim() !== '' || self.category() !== '') && !self.isSearching();
    });
    self.hasConfiguredIndexers = ko.pureComputed(function() { return self.configuredIndexers().length > 0; });
    // Only after capabilities have actually loaded, so the empty-state notice
    // doesn't flash on screen while that first request is still in flight
    self.showNoIndexersNotice = ko.pureComputed(function() {
        return self.capabilitiesLoaded() && !self.hasConfiguredIndexers();
    });

    // Load the merged category tree and the list of configured indexers (once).
    // Deferred until the modal is first opened so a page load never hits the indexers.
    var capabilitiesRequested = false;
    self.loadCapabilities = function() {
        if (capabilitiesRequested) return;
        capabilitiesRequested = true;
        callAPI({ mode: 'nzbsearch', name: 'caps' }, 30000).done(function(response) {
            var data = response.nzbsearch || {};
            self.categories(data.categories || []);
            self.configuredIndexers(data.indexers || []);
            self.capabilitiesLoaded(true);
        }).fail(function() {
            capabilitiesRequested = false;
        });
    };

    self.runSearch = function() {
        if (!self.canSearch()) return;

        self.isSearching(true);
        callAPI({
            mode: 'nzbsearch',
            search: self.searchTerm(),
            cat: self.category()
        }, 30000).done(function(response) {
            var data = response.nzbsearch || {};
            self.results(ko.utils.arrayMap(data.results || [], function(item) {
                return new NzbSearchResult(item);
            }));
            self.totalItems(data.total_available || 0);
            self.hasSearched(true);
        }).always(function() {
            self.isSearching(false);
        });
    };

    self.submit = self.runSearch;
}


/**
    A single search result row
**/
function NzbSearchResult(data) {
    var self = this;

    self.title = data.title;
    self.url = data.url;
    self.baselink = data.baselink;
    self.faviconUrl = self.baselink ? ('//' + self.baselink + '/favicon.ico') : '';
    self.category = data.category;
    self.sizeText = data.size_str || '';
    self.ageText = data.age || '';
    self.hasPassword = !!data.password;
    self.detailsUrl = data.details_url || '';
    self.categoryText = self.category;

    // Open the Add NZB modal, pre-filled, instead of adding straight to the queue -
    // stacked on top of the still-open search modal rather than replacing it
    self.openAddModal = function() {
        var addNzbModal = $('#modal-add-nzb');
        addNzbModal.find('input[name="nzbURL"]').val(self.url);
        $('#nzbname').val(self.title);

        addNzbModal.addClass('nzbsearch-stacked').one('shown.bs.modal', function() {
            $('.modal-backdrop').last().addClass('nzbsearch-stacked-backdrop');
        }).one('hidden.bs.modal', function() {
            addNzbModal.removeClass('nzbsearch-stacked');
            // Bootstrap always strips this on hide, even though the search modal stays open
            if ($('#modal-nzbsearch').hasClass('in')) {
                $(document.body).addClass('modal-open');
            }
        }).modal('show');
    };
}

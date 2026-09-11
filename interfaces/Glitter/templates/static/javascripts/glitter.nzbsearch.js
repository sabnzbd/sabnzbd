/**
    Model behind the newznab indexer search modal (#modal-nzbsearch)
**/
function NzbSearchModel(parent) {
    var self = this;
    self.parent = parent;

    // Query state
    self.searchTerm = ko.observable('');
    self.category = ko.observable('').extend({ persist: 'nzbSearchCategory' });
    self.pageSize = ko.observable(50).extend({ persist: 'nzbSearchPageSize' });
    self.offset = ko.observable(0);

    // Category applied to jobs added from the results (empty = the result's own
    // mapped category, or the Default category); priority/pp/script then follow
    // from that category, exactly as a plain addurl would.
    self.addCategory = ko.observable('');

    // Result state
    self.results = ko.observableArray([]);
    self.indexerStatus = ko.observableArray([]);
    self.categories = ko.observableArray([]);
    self.configuredIndexers = ko.observableArray([]);
    self.capabilitiesLoaded = ko.observable(false);
    self.totalFound = ko.observable(0);
    self.totalAvailable = ko.observable(0);
    self.isSearching = ko.observable(false);
    self.hasSearched = ko.observable(false);

    // Flat <option> list: each top-level category followed by its indented subcats
    self.categoryOptions = ko.pureComputed(function() {
        var options = [{ value: '', label: glitterTranslate.nzbsearch.allCategories }];
        ko.utils.arrayForEach(self.categories(), function(category) {
            options.push({ value: String(category.id), label: category.name });
            ko.utils.arrayForEach(category.subcats, function(sub) {
                options.push({ value: String(sub.id), label: '   ' + sub.name });
            });
        });
        return options;
    });

    self.hasResults = ko.pureComputed(function() { return self.results().length > 0; });
    self.canSearch = ko.pureComputed(function() {
        return (self.searchTerm().trim() !== '' || self.category() !== '') && !self.isSearching();
    });
    self.hasConfiguredIndexers = ko.pureComputed(function() { return self.configuredIndexers().length > 0; });
    // Only after capabilities have actually loaded, so the empty-state notice
    // doesn't flash on screen while that first request is still in flight
    self.showNoIndexersNotice = ko.pureComputed(function() {
        return self.capabilitiesLoaded() && !self.hasConfiguredIndexers();
    });
    self.canPrevPage = ko.pureComputed(function() { return self.offset() > 0; });
    self.canNextPage = ko.pureComputed(function() {
        return (self.offset() + self.pageSize()) < self.totalAvailable();
    });
    self.rangeText = ko.pureComputed(function() {
        if (!self.hasResults()) return '';
        return (self.offset() + 1) + '–' + (self.offset() + self.results().length) +
            ' / ' + self.totalAvailable();
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

    self.runSearch = function(keepOffset) {
        if (!keepOffset) self.offset(0);
        if (!self.canSearch() && !self.isSearching()) return;

        self.isSearching(true);
        callAPI({
            mode: 'nzbsearch',
            q: self.searchTerm(),
            cat: self.category(),
            offset: self.offset(),
            limit: self.pageSize()
        }, 30000).done(function(response) {
            var data = response.nzbsearch || {};
            self.results(ko.utils.arrayMap(data.results || [], function(item) {
                return new NzbSearchResult(item, self);
            }));
            self.indexerStatus(data.indexers || []);
            self.totalFound(data.total || 0);
            self.totalAvailable(data.total_available || 0);
            self.hasSearched(true);
        }).always(function() {
            self.isSearching(false);
        });
    };

    self.submit = function() { self.runSearch(false); };
    self.nextPage = function() {
        self.offset(self.offset() + self.pageSize());
        self.runSearch(true);
    };
    self.prevPage = function() {
        self.offset(Math.max(0, self.offset() - self.pageSize()));
        self.runSearch(true);
    };

    // Human label for one indexer's outcome, e.g. "12 / 340" or "Auth failed"
    self.indexerStatusText = function(status) {
        if (status.status === 'ok') {
            return status.results + ' / ' + (status.total || status.results);
        }
        return glitterTranslate.nzbsearch.status[status.status] || status.status;
    };
    self.indexerStatusOk = function(status) { return status.status === 'ok'; };
}


/**
    A single search result row
**/
function NzbSearchResult(data, searchModel) {
    var self = this;
    self.search = searchModel;

    self.title = data.title;
    self.url = data.url;
    self.indexer = data.indexer;
    self.category = data.category;
    self.categoryIds = data.category_ids || [];
    self.sizeText = data.size_str || '';
    self.ageText = (data.age_days === null || data.age_days === undefined) ? '–' : (data.age_days + 'd');
    self.grabs = data.grabs || 0;
    self.hasPassword = !!data.password;
    self.detailsUrl = data.details_url || '';
    self.sabCategory = data.sab_category || '';

    self.isAdding = ko.observable(false);
    self.isAdded = ko.observable(false);

    self.addToQueue = function() {
        if (self.isAdded()) return;
        self.isAdding(true);
        callAPI({
            mode: 'addurl',
            name: self.url,
            nzbname: self.title,
            cat: self.search.addCategory() || self.sabCategory
        }).done(function() {
            self.isAdded(true);
            self.search.parent.refresh();
        }).always(function() {
            self.isAdding(false);
        });
    };
}

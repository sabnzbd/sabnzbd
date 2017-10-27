/**
    Model for the whole Queue with all it's items
**/
function QueueListModel(parent) {
    // Internal var's
    var self = this;
    self.parent = parent;
    self.dragging = false;
    self.rawCatList = [];
    self.rawScriptList = [];

    // Because SABNZB returns the name
    // But when you want to set Priority you need the number..
    self.priorityName = [];
    self.priorityName["Force"] = 2;
    self.priorityName["High"] = 1;
    self.priorityName["Normal"] = 0;
    self.priorityName["Low"] = -1;
    self.priorityName["Stop"] = -4;
    self.priorityOptions = ko.observableArray([
        { value: 2,  name: glitterTranslate.priority["Force"] },
        { value: 1,  name: glitterTranslate.priority["High"] },
        { value: 0,  name: glitterTranslate.priority["Normal"] },
        { value: -1, name: glitterTranslate.priority["Low"] },
        { value: -4, name: glitterTranslate.priority["Stop"] }
    ]);
    self.processingOptions = ko.observableArray([
        { value: 0, name: glitterTranslate.pp["Download"] },
        { value: 1, name: glitterTranslate.pp["+Repair"] },
        { value: 2, name: glitterTranslate.pp["+Unpack"] },
        { value: 3, name: glitterTranslate.pp["+Delete"] }
    ]);

    // External var's
    self.queueItems = ko.observableArray([]);
    self.totalItems = ko.observable(0);
    self.isMultiEditing = ko.observable(false);
    self.isLoading = ko.observable(false).extend({ rateLimit: 100 });
    self.multiEditItems = ko.observableArray([]);
    self.categoriesList = ko.observableArray([]);
    self.scriptsList = ko.observableArray([]);
    self.searchTerm = ko.observable('').extend({ rateLimit: { timeout: 200, method: "notifyWhenChangesStop" } });
    self.paginationLimit = ko.observable(20).extend({ persist: 'queuePaginationLimit' });
    self.pagination = new paginationModel(self);

    // Don't update while dragging
    self.shouldUpdate = function() {
        return !self.dragging;
    }
    self.dragStart = function() {
        self.dragging = true;
    }
    self.dragStop = function(event) {
        // Remove that extra label
        $(event.target).parent().removeClass('table-active-sorting')
        // Wait a little before refreshing again (prevents jumping)
        setTimeout(function() {
            self.dragging = false;
        }, 500)
    }

    // Update slots from API data
    self.updateFromData = function(data) {
        // Get all ID's
        var itemIds = $.map(self.queueItems(), function(i) {
            return i.id;
        });

        // Did the category-list change?
        // Otherwise KO will send updates to all <select> for every refresh()
        if(self.rawCatList != data.categories.toString()) {
            // Reformat categories
            self.categoriesList($.map(data.categories, function(cat) {
                // Default?
                if(cat == '*') return { catValue: '*', catText: glitterTranslate.defaultText };
                return { catValue: cat, catText: cat };
            }))
            // Update
            self.rawCatList = data.categories.toString();
        }

        // Did the script-list change?
        if(self.rawScriptList != data.scripts.toString()) {
            // Reformat script-list
            self.scriptsList($.map(data.scripts, function(script) {
                // Default?
                if(script == 'None') return glitterTranslate.noneText;
                return script;
            }))
            // Update
            self.rawScriptList = data.scripts.toString();
        }

        // Set limit
        self.totalItems(data.noofslots);

        // Container for new models
        var newItems = [];

        // Go over all items
        $.each(data.slots, function() {
            var item = this;
            var existingItem = ko.utils.arrayFirst(self.queueItems(), function(i) {
                return i.id == item.nzo_id;
            });

            if(existingItem) {
                existingItem.updateFromData(item);
                itemIds.splice(itemIds.indexOf(item.nzo_id), 1);
            } else {
                // Add new item
                newItems.push(new QueueModel(self, item))
            }
        });

        // Remove all items if there's any
        if(itemIds.length == self.paginationLimit()) {
            // Replace it, so only 1 Knockout DOM-update!
            self.queueItems(newItems);
            newItems = [];
        } else {
            // Remove items that don't exist anymore
            $.each(itemIds, function() {
                var id = this.toString();
                self.queueItems.remove(ko.utils.arrayFirst(self.queueItems(), function(i) {
                    return i.id == id;
                }));
            });
        }

        // New items, then add!
        if(newItems.length > 0) {
            ko.utils.arrayPushAll(self.queueItems, newItems);
            self.queueItems.valueHasMutated();
        }

        // Sort every time (takes just few msec)
        self.queueItems.sort(function(a, b) {
            return a.index() < b.index() ? -1 : 1;
        });
    };

    // Move in sortable
    self.move = function(event) {
        var itemMoved = event.item;
        // Up or down?
        var corTerm = event.targetIndex > event.sourceIndex ? -1 : 1;
        // See what the actual index is of the queue-object
        // This way we can see how we move up and down independent of pagination
        var itemReplaced = self.queueItems()[event.targetIndex+corTerm];
        callAPI({
            mode: "switch",
            value: itemMoved.id,
            value2: itemReplaced.index()
        }).then(self.parent.refresh);
    };

    // Move button clicked
    self.moveButton = function(event,ui) {
        var itemMoved = event;
        var targetIndex;
        if($(ui.currentTarget).is(".buttonMoveToTop")){
            //we want to move to the top
            targetIndex = 0;
        } else {
            // we want to move to the bottom
			targetIndex = self.totalItems() - 1;
        }
        callAPI({
            mode: "switch",
            value: itemMoved.id,
            value2: targetIndex
        }).then(self.parent.refresh);

    }

    // Save pagination state
    self.paginationLimit.subscribe(function(newValue) {
        // Save in config if global
        if(self.parent.useGlobalOptions()) {
            callAPI({
                mode: "set_config",
                section: "misc",
                keyword: "queue_limit",
                value: newValue
            })
        }
    });

    // Do we show search box. So it doesn't dissapear when nothing is found
    self.hasQueueSearch = ko.pureComputed(function() {
        return (self.pagination.hasPagination() || self.searchTerm() || (self.parent.hasQueue() && self.isMultiEditing()))
    })

    // Searching in queue (rate-limited in decleration)
    self.searchTerm.subscribe(function() {
        // Refresh now
        self.parent.refresh();
        // Go back to page 1
        if(self.pagination.currentPage() != 1) {
            self.pagination.moveToPage(1);
        }
    })

    // Clear searchterm
    self.clearSearchTerm = function(data, event) {
        // Was it escape key or click?
        if(event.type == 'mousedown' || (event.keyCode && event.keyCode == 27)) {
            self.isLoading(true)
            self.searchTerm('');
            self.parent.refresh()
        }
        // Was it click and the field is empty? Then we focus on the field
        if(event.type == 'mousedown' && self.searchTerm() == '') {
            $(event.target).parents('.search-box').find('input[type="text"]').focus()
            return;
        }
        // Need to return true to allow typing
        return true;
    }

    /***
        Multi-edit functions
    ***/
    self.queueSorting = function(data, event) {
        // What action?
        var sort, dir;
        switch($(event.currentTarget).data('action')) {
            case 'sortAgeAsc':
                sort = 'avg_age';
                dir = 'asc';
                break;
            case 'sortAgeDesc':
                sort = 'avg_age';
                dir = 'desc';
                break;
            case 'sortNameAsc':
                sort = 'name';
                dir = 'asc';
                break;
            case 'sortNameDesc':
                sort = 'name';
                dir = 'desc';
                break;
            case 'sortSizeAsc':
                sort = 'size';
                dir = 'asc';
                break;
            case 'sortSizeDesc':
                sort = 'size';
                dir = 'desc';
                break;
        }

        // Show notification
        showNotification('.main-notification-box-sorting', 2000)

        // Send call
        callAPI({
            mode: 'queue',
            name: 'sort',
            sort: sort,
            dir: dir
        }).then(parent.refresh)
    }

    // Show the input box
    self.showMultiEdit = function() {
        // Update value
        self.isMultiEditing(!self.isMultiEditing())
        // Form
        var $form = $('form.multioperations-selector')

        // Reset form and remove all checked ones
        $form[0].reset();
        self.multiEditItems.removeAll();
        $('.delete input[name="multiedit"], #multiedit-checkall').prop({'checked': false, 'indeterminate': false})

        // Is the multi-edit in view?
        if(($form.offset().top + $form.outerHeight(true)) > ($(window).scrollTop()+$(window).height())) {
            // Scroll to form
            $('html, body').animate({
                scrollTop: $form.offset().top + $form.outerHeight(true) - $(window).height() + 'px'
            }, 'fast')
        }
    }

    // Add to the list
    self.addMultiEdit = function(item, event) {
        // Is it a shift-click?
        if(event.shiftKey) {
            checkShiftRange('.queue-table input[name="multiedit"]');
        }

        // Add or remove from the list?
        if(event.currentTarget.checked) {
            // Add item
            self.multiEditItems.push(item);
            // Update them all
            self.doMultiEditUpdate();
        } else {
            // Go over them all to know which one to remove
            self.multiEditItems.remove(function(inList) { return inList.id == item.id; })
        }

        // Update check-all buton state
        setCheckAllState('#multiedit-checkall', '.queue-table input[name="multiedit"]')
        return true;
    }

    // Check all
    self.checkAllJobs = function(item, event) {
        // Get which ones we care about
        var allChecks = $('.queue-table input[name="multiedit"]').filter(':not(:disabled):visible');

        // We need to re-evaltuate the state of this check-all
        // Otherwise the 'inderterminate' will be overwritten by the click event!
        setCheckAllState('#multiedit-checkall', '.queue-table input[name="multiedit"]')

        // Now we can check what happend
        // For when some are checked, or all are checked (but not partly)
        if(event.target.indeterminate || (event.target.checked && !event.target.indeterminate)) {
            var allActive = allChecks.filter(":checked")
            // First remove the from the list
            if(allActive.length == self.multiEditItems().length) {
                // Just remove all
                self.multiEditItems.removeAll();
                // Remove the check
                allActive.prop('checked', false)
            } else {
                // Remove them seperate
                allActive.each(function() {
                    // Go over them all to know which one to remove
                    var item = ko.dataFor(this)
                    self.multiEditItems.remove(function(inList) { return inList.id == item.id; })
                    // Remove the check of this one
                    this.checked = false;
                })
            }
        } else {
            // None are checked, so check and add them all
            allChecks.prop('checked', true)
            allChecks.each(function() { self.multiEditItems.push(ko.dataFor(this)) })
            event.target.checked = true

            // Now we fire the update
            self.doMultiEditUpdate()
        }
        // Set state of all the check-all's
        setCheckAllState('#multiedit-checkall', '.queue-table input[name="multiedit"]')
        return true;
    }

    // Do the actual multi-update immediatly
    self.doMultiEditUpdate = function() {
        // Anything selected?
        if(self.multiEditItems().length < 1) return;

        // Retrieve the current settings
        var newCat = $('.multioperations-selector select[name="Category"]').val()
        var newScript = $('.multioperations-selector select[name="Post-processing"]').val()
        var newPrior = $('.multioperations-selector select[name="Priority"]').val()
        var newProc = $('.multioperations-selector select[name="Processing"]').val()
        var newStatus = $('.multioperations-selector input[name="multiedit-status"]:checked').val()

        // List all the ID's
        var  strIDs = '';
        $.each(self.multiEditItems(), function(index) {
            strIDs = strIDs + this.id + ',';
        })

        // What is changed?
        if(newCat != '') {
            callAPI({
                mode: 'change_cat',
                value: strIDs,
                value2: newCat
            })
        }
        if(newScript != '') {
            callAPI({
                mode: 'change_script',
                value: strIDs,
                value2: newScript
            })
        }
        if(newPrior != '') {
            callAPI({
                mode: 'queue',
                name: 'priority',
                value: strIDs,
                value2: newPrior
            })
        }
        if(newProc != '') {
            callAPI({
                mode: 'change_opts',
                value: strIDs,
                value2: newProc
            })
        }
        if(newStatus) {
            callAPI({
                mode: 'queue',
                name: newStatus,
                value: strIDs
            })
        }

        // Wat a little and do the refresh
        // Only if anything changed!
        if(newStatus || newProc != '' || newPrior != '' || newScript != '' || newCat != '') {
            setTimeout(parent.refresh, 100)
        }
    }

    // Selete all selected
    self.doMultiDelete = function() {
        // Anything selected?
        if(self.multiEditItems().length < 1) return;

        // Need confirm
        if(!self.parent.confirmDeleteQueue() || confirm(glitterTranslate.removeDown)) {
            // List all the ID's
            var strIDs = '';
            $.each(self.multiEditItems(), function(index) {
                strIDs = strIDs + this.id + ',';
            })

            // Show notification
            showNotification('.main-notification-box-removing-multiple', 0, self.multiEditItems().length)

            // Remove
            callAPI({
                mode: 'queue',
                name: 'delete',
                del_files: 1,
                value: strIDs
            }).then(function(response) {
                if(response.status) {
                    // Make sure the queue doesnt flicker and then fade-out
                    self.isLoading(true)
                    $('.delete input:checked').parents('tr').fadeOut(fadeOnDeleteDuration)
                    self.parent.refresh()
                    // Empty it
                    self.multiEditItems.removeAll();
                    // Hide notification
                    hideNotification(true)
                }
            })
        }
    }

    // On change of page we need to check all those that were in the list!
    self.queueItems.subscribe(function() {
        // We need to wait until the unit is actually finished rendering
        setTimeout(function() {
            $.each(self.multiEditItems(), function(index) {
                $('#multiedit_' + this.id).prop('checked', true);
            })

            // Update check-all buton state
            setCheckAllState('#multiedit-checkall', '.queue-table input[name="multiedit"]')
        }, 100)
    }, null, "arrayChange")
}

/**
    Model for each Queue item
**/
function QueueModel(parent, data) {
    var self = this;
    self.parent = parent;

    // Job info
    self.id = data.nzo_id;
    self.name = ko.observable($.trim(data.filename));
    self.password = ko.observable(data.password);
    self.index = ko.observable(data.index);
    self.status = ko.observable(data.status);
    self.isGrabbing = ko.observable(data.status == 'Grabbing' || data.avg_age == '-')
    self.isFetchingBlocks = data.status == 'Fetching' || data.priority == 'Repair' // No need to update
    self.totalMB = ko.observable(parseFloat(data.mb));
    self.remainingMB = ko.observable(parseFloat(data.mbleft))
    self.missingMB = ko.observable(parseFloat(data.mbmissing))
    self.percentage = ko.observable(parseInt(data.percentage))
    self.avg_age = ko.observable(data.avg_age)
    self.direct_unpack = ko.observable(data.direct_unpack)
    self.category = ko.observable(data.cat);
    self.priority = ko.observable(parent.priorityName[data.priority]);
    self.script = ko.observable(data.script);
    self.unpackopts = ko.observable(parseInt(data.unpackopts)) // UnpackOpts fails if not parseInt'd!
    self.pausedStatus = ko.observable(data.status == 'Paused');
    self.timeLeft = ko.observable(data.timeleft);

    // Initially empty
    self.nameForEdit = ko.observable();
    self.editingName = ko.observable(false);
    self.hasDropdown = ko.observable(false);

    // Color of the progress bar
    self.progressColor = ko.computed(function() {
        // Checking
        if(self.status() == 'Checking') {
            return '#58A9FA'
        }
        // Check for missing data, the value is arbitrary! (2%)
        if(self.missingMB()/self.totalMB() > 0.02) {
            return '#F8A34E'
        }
        // Set to grey, only when not Force download
        if((self.parent.parent.downloadsPaused() && self.priority() != 2) || self.pausedStatus()) {
            return '#B7B7B7'
        }
        // Nothing
        return '';
    });

    // MB's
    self.progressText = ko.pureComputed(function() {
        return (self.totalMB() - self.remainingMB()).toFixed(0) + " MB / " + (self.totalMB() * 1).toFixed(0) + " MB";
    })

    // Texts
    self.name_title = ko.pureComputed(function() {
        // When hovering over the job
        if(self.direct_unpack()) {
            return self.name() + ' - ' + glitterTranslate.status['DirectUnpack'] + ': ' + self.direct_unpack()
        }
        return self.name()
    })
    self.missingText = ko.pureComputed(function() {
        // Check for missing data, the value is arbitrary! (1%)
        if(self.missingMB()/self.totalMB() > 0.01) {
            return self.missingMB().toFixed(0) + ' MB ' + glitterTranslate.misingArt
        }
        return;
    })
    self.statusText = ko.computed(function() {
        // Checking
        if(self.status() == 'Checking') {
            return glitterTranslate.checking
        }
        // Grabbing
        if(self.status() == 'Grabbing') {
            return glitterTranslate.fetch
        }
        // Pausing status
        if((self.parent.parent.downloadsPaused() && self.priority() != 2) || self.pausedStatus()) {
            return glitterTranslate.paused;
        }
        // Just the time
        return rewriteTime(self.timeLeft());
    });

    // Icon to better show force-priority
    self.queueIcon = ko.computed(function() {
        // Force comes first
        if(self.priority() == 2) {
            return 'glyphicon-forward'
        }
        if(self.pausedStatus()) {
            return 'glyphicon-play'
        }
        return 'glyphicon-pause'
    })

    // Extra queue column
    self.extraText = ko.pureComputed(function() {
        // Picked anything?
        switch(self.parent.parent.extraQueueColumn()) {
            case 'category':
                // Exception for *
                if(self.category() == "*")
                    return glitterTranslate.defaultText
                return self.category();
            case 'priority':
                // Onload-exception
                if(self.priority() == undefined) return;
                return ko.utils.arrayFirst(self.parent.priorityOptions(), function(item) { return item.value == self.priority()}).name;
            case 'processing':
                // Onload-exception
                if(self.unpackopts() == undefined) return;
                return ko.utils.arrayFirst(self.parent.processingOptions(), function(item) { return item.value == self.unpackopts()}).name;
            case 'scripts':
                return self.script();
            case 'age':
                return self.avg_age();
        }
        return;
    })

    // Every update
    self.updateFromData = function(data) {
        // Update job info
        self.name($.trim(data.filename));
        self.password(data.password);
        self.index(data.index);
        self.status(data.status)
        self.isGrabbing(data.status == 'Grabbing' || data.avg_age == '-')
        self.totalMB(parseFloat(data.mb));
        self.remainingMB(parseFloat(data.mbleft));
        self.missingMB(parseFloat(data.mbmissing))
        self.percentage(parseInt(data.percentage))
        self.avg_age(data.avg_age)
        self.direct_unpack(data.direct_unpack)
        self.category(data.cat);
        self.priority(parent.priorityName[data.priority]);
        self.script(data.script);
        self.unpackopts(parseInt(data.unpackopts)) // UnpackOpts fails if not parseInt'd!
        self.pausedStatus(data.status == 'Paused');
        self.timeLeft(data.timeleft);
    };

    // Pause individual download
    self.pauseToggle = function() {
        callAPI({
            mode: 'queue',
            name: (self.pausedStatus() ? 'resume' : 'pause'),
            value: self.id
        }).then(self.parent.parent.refresh);
    };

    // Edit name
    self.editName = function(data, event) {
        // Not when still grabbing
        if(self.isGrabbing()) return false;

        // Change status and fill
        self.editingName(true)
        self.nameForEdit(self.name())

        // Select
        $(event.target).parents('.name').find('input').select()
    }

    // Catch the submit action
    self.editingNameSubmit = function() {
        self.editingName(false)
    }

    // Do on change
    self.nameForEdit.subscribe(function(newName) {
        // Anything change or empty?
        if(!newName || self.name() == newName) return;

        // Send rename
        callAPI({
                mode: 'queue',
                name: 'rename',
                value: self.id,
                value2: newName
            }).then(self.parent.parent.refresh)
    })

    // See items
    self.showFiles = function() {
        // Not when still grabbing
        if(self.isGrabbing()) return false;
        // Trigger update
        parent.parent.filelist.loadFiles(self)
    }

    // Toggle calculation of dropdown
    // Turns out that the <select> in the dropdown are a hugggeeee slowdown on initial load!
    // Only loading on click cuts half the speed (especially on large queues)
    self.toggleDropdown = function(item, event) {
        self.hasDropdown(true)
        // Keep it open!
        keepOpen(event.target)
    }

    // Change of settings
    self.changeCat = function(item, event) {
        callAPI({
            mode: 'change_cat',
            value: item.id,
            value2: item.category()
        }).then(function() {
            // Hide all tooltips before we refresh
            $('.queue-item-settings li').filter('[data-tooltip="true"]').tooltip('hide')
            self.parent.parent.refresh()
        })
    }
    self.changeScript = function(item) {
        // Not on empty handlers
        if(!item.script() || parent.scriptsList().length <= 1) return;
        callAPI({
            mode: 'change_script',
            value: item.id,
            value2: item.script()
        })
    }
    self.changeProcessing = function(item) {
        callAPI({
            mode: 'change_opts',
            value: item.id,
            value2: item.unpackopts()
        })
    }
    self.changePriority = function(item, event) {
        // Not if we are fetching extra blocks for repair!
        if(item.isFetchingBlocks) return
        callAPI({
            mode: 'queue',
            name: 'priority',
            value: item.id,
            value2: item.priority()
        }).then(function() {
            // Hide all tooltips before we refresh
            $('.queue-item-settings li').filter('[data-tooltip="true"]').tooltip('hide')
            self.parent.parent.refresh()
        })
    }

    // Remove 1 download from queue
    self.removeDownload = function(item, event) {
        // Confirm and remove
        if(!self.parent.parent.confirmDeleteQueue() || confirm(glitterTranslate.removeDow1)) {
            var itemToDelete = this;

            // Show notification
            showNotification('.main-notification-box-removing')

            callAPI({
                mode: 'queue',
                name: 'delete',
                del_files: 1,
                value: item.id
            }).then(function(response) {
                // Fade and remove
                $(event.currentTarget).parent().parent().fadeOut(fadeOnDeleteDuration, function() {
                    // Make sure no flickering (if there are more items left) and then remove
                    self.parent.isLoading(self.parent.totalItems() > 1)
                    parent.queueItems.remove(itemToDelete);
                    parent.multiEditItems.remove(function(inList) { return inList.id == itemToDelete.id; })
                    self.parent.parent.refresh();
                    // Hide notifcation
                    hideNotification(true)
                })
            });
        }
    };
}
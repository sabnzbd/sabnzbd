/**
    Model for the whole History with all its items
**/
function HistoryListModel(parent) {
    var self = this;
    self.parent = parent;

    // Variables
    self.lastUpdate = 0;
    self.historyItems = ko.observableArray([])
    self.showFailed = ko.observable(false).extend({ persist: 'historyShowFailed' });
    self.showArchive = ko.observable(false).extend({ persist: 'historyShowArchive' });
    self.permanentlyDelete = ko.observable(false).extend({ persist: 'permanentlyDelete' });
    self.isLoading = ko.observable(false).extend({ rateLimit: 100 });
    self.searchTerm = ko.observable('').extend({ rateLimit: { timeout: 400, method: "notifyWhenChangesStop" } });
    self.paginationLimit = ko.observable(10).extend({ persist: 'historyPaginationLimit' });
    self.totalItems = ko.observable(0);
    self.deleteItems = ko.observableArray([]);
    self.ppItems = ko.observable(0);
    self.pagination = new paginationModel(self);
    self.isMultiEditing = ko.observable(false).extend({ persist: 'historyIsMultiEditing' });
    self.multiEditItems = ko.observableArray([]);

    // Download history info
    self.downloadedToday = ko.observable();
    self.downloadedWeek = ko.observable();
    self.downloadedMonth = ko.observable();
    self.downloadedTotal = ko.observable();

    // Update function for history list
    self.updateFromData = function(data) {
        /***
            See if there's anything to update
        ***/
        if(!data) return;
        self.lastUpdate = data.last_history_update

        /***
            History list functions per item
        ***/
        var itemIds = $.map(self.historyItems(), function(i) {
            return i.historyStatus.nzo_id();
        });

        // For new items
        var newItems = [];
        $.each(data.slots, function(index, slot) {
            var existingItem = ko.utils.arrayFirst(self.historyItems(), function(i) {
                return i.historyStatus.nzo_id() === slot.nzo_id;
            });
            // Set index in the results
            slot.index = index

            // Update or add?
            if(existingItem) {
                existingItem.updateFromData(slot);
                itemIds.splice(itemIds.indexOf(slot.nzo_id), 1);
            } else {
                // Add history item
                newItems.push(new HistoryModel(self, slot));
            }
        });

        // Remove all items
        if(itemIds.length === self.paginationLimit()) {
            // Replace it, so only 1 Knockout DOM-update!
            self.historyItems(newItems);
            newItems = [];
        } else {
            // Remove the un-used ones
            $.each(itemIds, function() {
                var id = this.toString();
                self.historyItems.remove(ko.utils.arrayFirst(self.historyItems(), function(i) {
                    return i.historyStatus.nzo_id() === id;
                }));
            });
        }

        // Add new ones
        if(newItems.length > 0) {
            ko.utils.arrayPushAll(self.historyItems, newItems);
            self.historyItems.valueHasMutated();

            // We also check if it might be in the Multi-edit
            if(self.parent.queue.multiEditItems().length > 0) {
                $.each(newItems, function() {
                    var currentItem = this;
                    self.parent.queue.multiEditItems.remove(function(inList) { return inList.id === currentItem.id; })
                })
            }
        }

        // Sort every time (takes just few msec)
        self.historyItems.sort(function(a, b) {
            return a.index < b.index ? -1 : 1;
        });

        /***
            History information
        ***/
        self.totalItems(data.noofslots);
        self.ppItems(data.ppslots)
        self.downloadedToday(data.day_size);
        self.downloadedWeek(data.week_size);
        self.downloadedMonth(data.month_size);
        self.downloadedTotal(data.total_size);
    };

    // Save pagination state
    self.paginationLimit.subscribe(function(newValue) {
        // Save in config if global config
        if(self.parent.useGlobalOptions()) {
            callAPI({
                mode: "set_config",
                section: "misc",
                keyword: "history_limit",
                value: newValue
            })
        }
        // Update pagination and counters
        self.parent.refresh(true)
    });

    self.triggerRemoveDownload = function(items) {
        // Show and fill modal
        self.deleteItems.removeAll()

        // Single or multiple items?
        if(items.length) {
            ko.utils.arrayPushAll(self.deleteItems, items)
        } else {
            self.deleteItems.push(items)
        }

        // Show modal or delete right away
        if(self.parent.confirmDeleteHistory()) {
            // Open modal if desired
            $('#modal-delete-history-job').modal("show")
        } else {
            // Otherwise just submit right away
            $('#modal-delete-history-job form').submit()
        }
    }

    // Retry a job
    self.retryJob = function(form) {
        // Adding a extra retry file happens through this special function
        var data = new FormData();
        data.append("mode", "retry");
        data.append("nzbfile", $(form.nzbFile)[0].files[0]);
        data.append("value", $('#modal-retry-job input[name="retry_job_id"]').val());
        data.append("password", $('#retry_job_password').val());
        data.append("apikey", apiKey);

        // Add
        $.ajax({
            url: "./api",
            type: "POST",
            cache: false,
            processData: false,
            contentType: false,
            data: data
        }).then(function() {
            self.parent.refresh(true)
        });

        $("#modal-retry-job").modal("hide");
        $('.btn-file em').html(glitterTranslate.chooseFile + '&hellip;')
        form.reset()
    }

    // Searching in history (rate-limited in declaration)
    self.searchTerm.subscribe(function() {
        // Go back to page 1
        if(self.pagination.currentPage() !== 1) {
            // This forces a refresh
            self.pagination.moveToPage(1);
        } else {
            // Make sure we refresh
            self.parent.refresh(true);
        }
    })

    // Clear searchterm
    self.clearSearchTerm = function(data, event) {
        // Was it escape key or click?
        if(event.type === 'mousedown' || (event.keyCode && event.keyCode === 27)) {
            // Set the loader so it doesn't flicker and then switch
            self.isLoading(true)
            self.searchTerm('');
        }
        // Was it click and the field is empty? Then we focus on the field
        if(event.type === 'mousedown' && self.searchTerm() === '') {
            $(event.target).parents('.search-box').find('input[type="text"]').focus()
            return;
        }
        // Need to return true to allow typing
        return true;
    }

    // Toggle showing failed
    self.toggleShowFailed = function(data, event) {
        self.showFailed(!self.showFailed())
        // Force hide tooltip so it doesn't linger
        $('#history-options a').tooltip('hide')
        // Force refresh
        self.parent.refresh(true)
    }

    // Toggle showing archive
    self.toggleShowArchive = function(data, event) {
        self.showArchive(!self.showArchive())
        // Force hide tooltip so it doesn't linger
        $('#history-options a').tooltip('hide')
        // Force refresh
        self.parent.refresh(true)
    }

    // Retry all failed
    self.retryAllFailed = function(data, event) {
        // Ask to be sure
        if(confirm(glitterTranslate.retryAll)) {
            // Send the command
            callAPI({
                mode: 'retry_all'
            }).then(function() {
                // Force refresh
                self.parent.refresh(true)
            })
        }
    }

    // Empty history options
    self.emptyHistory = function(data, event) {
        // What event?
        var whatToRemove = $(event.target).data('action');
        var skipArchive = $('#modal-purge-history input[type="checkbox"]').prop("checked")
        var del_files, value;

        // Purge failed
        if(whatToRemove === 'history-purge-failed') {
            del_files = 0;
            value = 'failed';
        }
        // Also remove files
        if(whatToRemove === 'history-purgeremove-failed') {
            del_files = 1;
            value = 'failed';
        }
        // Remove completed
        if(whatToRemove === 'history-purge-completed') {
            del_files = 0;
            value = 'completed';
        }
        // Remove the ones on this page
        if(whatToRemove === 'history-purge-page') {
            // List all the ID's
            var strIDs = '';
            $.each(self.historyItems(), function(index) {
                // Only append when it's a download that can be deleted
                if(!this.processingDownload() && !this.processingWaiting()) {
                    strIDs = strIDs + this.id + ',';
                }
            })
            // Send the command
            callAPI({
                mode: 'history',
                name: 'delete',
                del_files: 1,
                archive: (!skipArchive) * 1,
                value: strIDs
            }).then(function() {
                // Clear search, refresh and hide
                self.searchTerm('');
                self.parent.refresh();
                $("#modal-purge-history").modal('hide');
            })
            return;
        }

        // Call API and close the window
        callAPI({
            mode: 'history',
            name: 'delete',
            del_files: del_files,
            archive: (!skipArchive) * 1,
            value: value
        }).then(function() {
            self.parent.refresh();
            $("#modal-purge-history").modal('hide');
        });
    };

    // Show the input checkbox
    self.showMultiEdit = function() {
        self.isMultiEditing(!self.isMultiEditing())
        self.multiEditItems.removeAll();
        $('.history-table input[name="multiedit"], #multiedit-checkall-history').prop({'checked': false, 'indeterminate': false})
    }

    // Add to the list
    self.addMultiEdit = function(item, event) {
        // Is it a shift-click?
        if(event.shiftKey) {
            checkShiftRange('.history-table input[name="multiedit"]');
        }

        // Add or remove from the list?
        if(event.currentTarget.checked) {
            // Add item
            self.multiEditItems.push(item);
        } else {
            // Go over them all to know which one to remove
            self.multiEditItems.remove(function(inList) { return inList.id == item.id; })
        }

        // Update check-all buton state
        setCheckAllState('#multiedit-checkall-history', '.history-table input[name="multiedit"]')
        return true;
    }

    // Check all
    self.checkAllJobs = function(item, event) {
        // Get which ones we care about
        var allChecks = $('.history-table input[name="multiedit"]').filter(':not(:disabled):visible');

        // We need to re-evaltuate the state of this check-all
        // Otherwise the 'inderterminate' will be overwritten by the click event!
        setCheckAllState('#multiedit-checkall-history', '.history-table input[name="multiedit"]')

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
        }
        // Set state of all the check-all's
        setCheckAllState('#multiedit-checkall-history', '.history-table input[name="multiedit"]')
        return true;
    }

    // Remove downloads from history
    self.removeDownloads = function(form) {
        // Hide modal and show notification
        $('#modal-delete-history-job').modal("hide")
        showNotification('.main-notification-box-removing')

        var strIDsPP = '';
        var strIDsHistory = '';
        $.each(self.deleteItems(), function(index) {
            // Split in jobs that need post-processing aborted, and jobs that need to be deleted
            if(this.processingDownload() === 2) {
                strIDsPP = strIDsPP + this.id + ',';
                // These items should not be listed in the deletedItems later on
                // as active post-processing aren't removed from the history output
                self.deleteItems.remove(this)
            } else {
                strIDsHistory = strIDsHistory + this.id + ',';
            }
        })

        // Trigger post-processing aborting
        if(strIDsPP !== "") {
            callAPI({
                mode: 'cancel_pp',
                value: strIDsPP
            }).then(function(response) {
                // Only hide and refresh
                self.parent.refresh();
                hideNotification()
            });
        }
        if(strIDsHistory !== "") {
            var skipArchive = $('#modal-delete-history-job input[type="checkbox"]').prop("checked")

            // Permanently delete if we are on the Archive page
            if(self.showArchive()) skipArchive = true

            callAPI({
                mode: 'history',
                name: 'delete',
                del_files: 1,
                archive: (!skipArchive) * 1,
                value: strIDsHistory
            }).then(function(response) {
                self.historyItems.removeAll(self.deleteItems());
                self.multiEditItems.removeAll(self.deleteItems())
                self.parent.refresh();
                hideNotification()
            });
        }
    };

    // Delete all selected
    self.doMultiDelete = function() {
        // Anything selected?
        if(self.multiEditItems().length < 1) return;

        // Trigger modal
        self.triggerRemoveDownload(self.multiEditItems())
    }

    // Mark jobs as completed
    self.markAsCompleted = function(items) {
        // Confirm
        if(!confirm(glitterTranslate.markComplete)) {
            return
        }
        // Single or multiple items?
        var strIDs = '';
        if(items.length) {
            $.each(items, function(index) {
                strIDs = strIDs + this.id + ',';
            })
        } else {
            strIDs = items.id
        }

        // Send the API call
        callAPI({
            mode: 'history',
            name: 'mark_as_completed',
            value: strIDs
        }).then(function(response) {
            // Force refresh to update the UI
            self.parent.refresh(true);
        });
    }

    // Mark all selected as completed
    self.doMultiMarkCompleted = function() {
        // Anything selected?
        if(self.multiEditItems().length < 1) return;

        // Mark them
        self.markAsCompleted(self.multiEditItems());
    }

    // Focus on the confirm button
    $('#modal-delete-history-job').on("shown.bs.modal", function() {
        $('#modal-delete-history-job .btn[type="submit"]').focus()
    })

    // On change of page we need to check all those that were in the list!
    self.historyItems.subscribe(function() {
        // We need to wait until the unit is actually finished rendering
        setTimeout(function() {
            $.each(self.multiEditItems(), function(index) {
                $('#multiedit_' + this.id).prop('checked', true);
            })

            // Update check-all buton state
            setCheckAllState('#multiedit-checkall-history', '.history-table input[name="multiedit"]')
        }, 100)
    }, null, "arrayChange")
}

/**
    Model for each History item
**/
function HistoryModel(parent, data) {
    var self = this;
    self.parent = parent;

    // We only update the whole set of information on first add
    // If we update the full set every time it uses lot of CPU
    // The Status/Actionline/scriptline/completed we do update every time
    // When clicked on the more-info button we load the rest again
    self.id = data.nzo_id;
    self.index = data.index;
    self.updateAllHistory = false;
    self.hasDropdown = ko.observable(false);
    self.historyStatus = ko.mapping.fromJS(data);
    self.status = ko.observable(data.status);
    self.action_line = ko.observable(data.action_line);
    self.script_line = ko.observable(data.script_line);
    self.fail_message = ko.observable(data.fail_message);
    self.completed = ko.observable(data.completed);
    self.canRetry = ko.observable(data.retry);

    // Update function
    self.updateFromData = function(data) {
        // Fill all the basic info
        self.index = data.index
        self.status(data.status)
        self.action_line(data.action_line)
        self.script_line(data.script_line)
        self.fail_message(data.fail_message)
        self.completed(data.completed)
        self.canRetry(data.retry)

        // Update all ONCE?
        if(self.updateAllHistory) {
            ko.mapping.fromJS(data, {}, self.historyStatus);
            self.updateAllHistory = false;
        }
    };

    // True/false if failed or not
    self.failed = ko.pureComputed(function() {
        return self.status() === 'Failed';
    });

    // Waiting?
    self.processingWaiting = ko.pureComputed(function() {
        return(self.status() === 'Queued')
    })

    // Processing or done?
    self.processingDownload = ko.pureComputed(function() {
        var status = self.status();
        // When we can cancel
        if (status === 'Extracting' || status === 'Verifying' || status === 'Repairing' || status === 'Running') {
            return 2
        }
        // These cannot be cancelled
        if(status === 'Moving') {
            return 1
        }
        return false;
    })

    // Format status text
    self.statusText = ko.pureComputed(function() {
        if(self.action_line() !== '')
            return self.action_line();
        if(self.status() === 'Failed') // Failed
            return self.fail_message();
        if(self.status() === 'Queued')
            return glitterTranslate.status['Queued'];
        if(self.script_line() === '') // No script line
            return glitterTranslate.status['Completed']

        return self.script_line();
    });

    // Extra history columns
    self.showColumn = function(param) {
        // Picked anything?
        switch(param) {
            case 'speed':
                // Anything to calculate?
                if(self.historyStatus.bytes() > 0 && self.historyStatus.download_time() > 0) {
                    try {
                        // Extract the Download section
                        var downloadLog = ko.utils.arrayFirst(self.historyStatus.stage_log(), function(item) {
                            return item.name() === 'Download'
                        });
                        // Extract the speed
                        return downloadLog.actions()[0].match(/(\S*\s\S+)(?=<br\/>)/)[0]
                    } catch(err) { }
                }
                return;
            case 'category':
                // Exception for *
                if(self.historyStatus.category() === "*")
                    return glitterTranslate.defaultText
                return self.historyStatus.category();
            case 'size':
                return self.historyStatus.size();
        }
        return;
    };

    // Format completion time
    self.completedOn = ko.pureComputed(function() {
        return displayDateTime(self.completed(), parent.parent.dateFormat(), 'X')
    });

    // Format time added
    self.timeAdded = ko.pureComputed(function() {
        return displayDateTime(self.historyStatus.time_added(), parent.parent.dateFormat(), 'X')
    });

    // Subscribe to retryEvent so we can load the password
    self.canRetry.subscribe(function() {
        self.updateAllHistory = true;
    })

    // Re-try button
    self.retry = function() {
        // Set JOB-id
        $('#modal-retry-job input[name="retry_job_id"]').val(self.id)
        // Set password
        $('#retry_job_password').val(self.historyStatus.password())
        // Open modal
        $('#modal-retry-job').modal("show")
    };

    // Mark as completed button
    self.markAsCompleted = function() {
        parent.markAsCompleted(self);
    };

    // Update information only on click
    self.updateAllHistoryInfo = function(data, event) {
        // Show
        self.hasDropdown(true);

        // Update all info
        self.updateAllHistory = true;
        parent.parent.refresh(true);

        // Try to keep open
        keepOpen(event.target)
    }

    // Use KO-afterRender to add the click-functionality always
    self.addHistoryStatusStuff = function(item) {
        $(item).find('.history-status-modallink a').click(function(e) {
            // Modal or 'More' click?
            if($(this).is('.history-status-dmca')) {
                // Pass
                return true;
            } else if($(this).is('.history-status-more')) {
                // Expand the rest of the text and hide the button
                $(this).siblings('.history-status-hidden').slideDown()
                $(this).hide()
            } else {
               // Info in modal
                $('#history-script-log .modal-body').load($(this).attr('href'), function(result) {
                    // Set title and then remove it
                    $('#history-script-log .modal-title').text($(this).find("h3").text())
                    $(this).find("h3, title").remove()
                    $('#history-script-log').modal('show');
                });
            }
            return false;
        })
    }
}
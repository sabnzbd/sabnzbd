/**
    Define main view model
**/
function ViewModel() {
    // Initialize models
    var self = this;
    self.queue = new QueueListModel(this);
    self.history = new HistoryListModel(this);
    self.filelist = new Fileslisting(this);

    // Set status varibales
    self.isRestarting = ko.observable(false);
    self.useGlobalOptions = ko.observable(true).extend({ persist: 'useGlobalOptions' });
    self.refreshRate = ko.observable(1).extend({ persist: 'pageRefreshRate' });
    self.dateFormat = ko.observable('fromNow').extend({ persist: 'pageDateFormat' });
    self.displayTabbed = ko.observable().extend({ persist: 'displayTabbed' });
    self.displayCompact = ko.observable(false).extend({ persist: 'displayCompact' });
    self.displayFullWidth = ko.observable(false).extend({ persist: 'displayFullWidth' });
    self.confirmDeleteQueue = ko.observable(true).extend({ persist: 'confirmDeleteQueue' });
    self.confirmDeleteHistory = ko.observable(true).extend({ persist: 'confirmDeleteHistory' });
    self.keyboardShortcuts = ko.observable(true).extend({ persist: 'keyboardShortcuts' });
    self.extraQueueColumns = ko.observableArray([]).extend({ persist: 'extraColumns' });
    self.extraHistoryColumns = ko.observableArray([]).extend({ persist: 'extraHistoryColumns' });
    self.showActiveConnections = ko.observable(false).extend({ persist: 'showActiveConnections' });
    self.speedMetrics = { '': "B/s", K: "KB/s", M: "MB/s", G: "GB/s" };

    // Set information varibales
    self.title = ko.observable();
    self.speed = ko.observable(0);
    self.speedMetric = ko.observable();
    self.bandwithLimit = ko.observable(false);
    self.pauseCustom = ko.observable('').extend({ rateLimit: { timeout: 200, method: "notifyWhenChangesStop" } });
    self.speedLimit = ko.observable(100).extend({ rateLimit: { timeout: 200, method: "notifyWhenChangesStop" } });
    self.speedLimitInt = ko.observable(false); // We need the 'internal' counter so we don't trigger the API all the time
    self.downloadsPaused = ko.observable(false);
    self.timeLeft = ko.observable("0:00");
    self.diskSpaceLeft1 = ko.observable();
    self.diskSpaceLeft2 = ko.observable();
    self.queueDataLeft = ko.observable();
    self.diskSpaceExceeded1 = ko.observable(false);
    self.diskSpaceExceeded2 = ko.observable(false);
    self.quotaLimit = ko.observable();
    self.quotaLimitLeft = ko.observable();
    self.systemLoad = ko.observable();
    self.cacheSize = ko.observable();
    self.cacheArticles = ko.observable();
    self.loglevel = ko.observable();
    self.nrWarnings = ko.observable(0);
    self.allWarnings = ko.observableArray([]);
    self.allMessages = ko.observableArray([]);
    self.finishaction = ko.observable();
    self.speedHistory = [];

    // Statusinfo container
    self.hasStatusInfo = ko.observable(false);
    self.hasPerformanceInfo = ko.observable(false);
    self.statusInfo = {};
    self.statusInfo.folders = ko.observableArray([]);
    self.statusInfo.servers = ko.observableArray([]);
    self.statusInfo.active_socks5_proxy = ko.observable();
    self.statusInfo.localipv4 = ko.observable();
    self.statusInfo.publicipv4 = ko.observable();
    self.statusInfo.ipv6 = ko.observable();
    self.statusInfo.dnslookup = ko.observable();
    self.statusInfo.delayed_assembler = ko.observable();
    self.statusInfo.loadavg = ko.observable();
    self.statusInfo.pystone = ko.observable();
    self.statusInfo.downloaddir = ko.observable();
    self.statusInfo.downloaddirspeed = ko.observable();
    self.statusInfo.completedir = ko.observable();
    self.statusInfo.completedirspeed = ko.observable();
    self.statusInfo.internetbandwidth = ko.observable();

    /***
        Dynamic functions
    ***/

    // Make the speedlimit tekst
    self.speedLimitText = ko.pureComputed(function() {
        // Set?
        if (!self.bandwithLimit()) return;

        // The text
        var bandwithLimitText = self.bandwithLimit().replace(/[^a-zA-Z]+/g, '');

        // Only the number
        var speedLimitNumberFull = (parseFloat(self.bandwithLimit()) * (self.speedLimit() / 100));

        // Trick to only get decimal-point when needed
        var speedLimitNumber = Math.round(speedLimitNumberFull * 10) / 10;

        // Fix it for lower than 1MB/s
        if (bandwithLimitText == 'M' && speedLimitNumber < 1) {
            bandwithLimitText = 'K';
            speedLimitNumber = Math.round(speedLimitNumberFull * 1024);
        }

        // Show text
        return self.speedLimit() + '% (' + speedLimitNumber + ' ' + self.speedMetrics[bandwithLimitText] + ')';
    });

    // Dynamic speed text function
    self.speedText = ko.pureComputed(function() {
        return self.speed() + ' ' + (self.speedMetrics[self.speedMetric()] ? self.speedMetrics[self.speedMetric()] : "B/s");
    });

    // Dynamic icon
    self.SABIcon = ko.pureComputed(function() {
        if (self.downloadsPaused()) {
            return './staticcfg/ico/faviconpaused.ico?v=1.1.0';
        } else {
            return './staticcfg/ico/favicon.ico?v=1.1.0';
        }
    })

    // Dynamic queue length check
    self.hasQueue = ko.pureComputed(function() {
        return (self.queue.queueItems().length > 0 || self.queue.searchTerm() || self.queue.isLoading())
    })

    // Dynamic history length check
    self.hasHistory = ko.pureComputed(function() {
        // We also 'have history' if we can't find any results of the search or there are no failed ones
        return (self.history.historyItems().length > 0 || self.history.searchTerm() || self.history.showFailed() || self.history.isLoading())
    })

    self.hasWarnings = ko.pureComputed(function() {
        return (self.allWarnings().length > 0)
    })

    // Check for any warnings/messages
    self.hasMessages = ko.pureComputed(function() {
        return parseInt(self.nrWarnings()) + self.allMessages().length;
    })

    self.updateCheckAllButtonState = function(section) {
        setCheckAllState('.multioperations-selector #multiedit-checkall', `.${section}-table input[name="multiedit"]`)
    }

    // Add queue or history item to multi-edit list
    self.addMultiEdit = function(item, event) {
        // The parent model is either the queue or history
        const model = this.parent;
        const section = model.queueItems ? 'queue' : 'history';

        if(event.shiftKey) {
            checkShiftRange(`.${section}-table input[name="multiedit"]`);
        }

        if(event.currentTarget.checked) {
            model.multiEditItems.push(item);

            // History is not editable
            // Only the queue will fire the multi-edit update
            model.doMultiEditUpdate?.();
        } else {
            model.multiEditItems.remove(function(inList) { return inList.id == item.id; })
        }

        self.updateCheckAllButtonState(section);
        return true;
    }
    
    // Check all queue or history items
    self.checkAllJobs = function(item, event) {
        const section = event.currentTarget.closest('.multioperations-selector').id === 'history-options' ? 'history' : 'queue';
        const model = section === 'history' ? self.history : self.queue;

        const allChecks = $(`.${section}-table input[name="multiedit"]`).filter(':not(:disabled):visible');

        self.updateCheckAllButtonState(section);

        if(event.target.indeterminate || (event.target.checked && !event.target.indeterminate)) {
            const allActive = allChecks.filter(":checked")
            if(allActive.length === model.multiEditItems().length) {
                model.multiEditItems.removeAll();
                allActive.prop('checked', false)
            } else {
                allActive.each(function() {
                    var item = ko.dataFor(this)
                    model.multiEditItems.remove(function(inList) { return inList.id === item.id; })
                    this.checked = false;
                })
            }
        } else {
            allChecks.prop('checked', true)
            allChecks.each(function() { model.multiEditItems.push(ko.dataFor(this)) })
            event.target.checked = true

            model.multiEditUpdate?.();
        }

        self.updateCheckAllButtonState(section);
        return true;
    }

    // Delete all selected queue or history items
    self.doMultiDelete = function(item, event) {
        const section = event.currentTarget.closest('.multioperations-selector').id === 'history-options' ? 'history' : 'queue';
        const model = section === 'history' ? self.history : self.queue;

        // Anything selected?
        if(model.multiEditItems().length < 1) return;

        if(!self.confirmDeleteHistory() || confirm(glitterTranslate.removeDown)) {
            let strIDs = '';
            $.each(model.multiEditItems(), function() {
                strIDs = strIDs + this.id + ',';
            })

            showNotification('.main-notification-box-removing-multiple', 0, model.multiEditItems().length)

            callAPI({
                mode: section,
                name: 'delete',
                del_files: 1,
                value: strIDs
            }).then(function(response) {
                if(response.status) {
                    // Make sure the history doesnt flicker and then fade-out
                    model.isLoading(true)
                    self.refresh()
                    model.multiEditItems.removeAll();
                    hideNotification()
                }
            })
        }
    }

    // Update main queue
    self.updateQueue = function(response) {
        // Block in case off dragging
        if (!self.queue.shouldUpdate()) return;

        // Make sure we are displaying the interface
        if (self.isRestarting() >= 1) {
            // Decrease the counter by 1
            // In case of restart (which takes time to fire) we count down
            // In case of re-connect after failure it counts from 1 so emmediate continuation
            self.isRestarting(self.isRestarting() - 1);
            return;
        }

        /***
            Possible login failure?
        ***/
        if (response.hasOwnProperty('error') && response.error == 'Missing authentication') {
            // Restart
            document.location = document.location;
        }

        /***
            Basic information
        ***/
        // Queue left
        self.queueDataLeft(response.queue.mbleft > 0 ? response.queue.sizeleft : '')

        // Paused?
        self.downloadsPaused(response.queue.paused);

        // Finish action. Replace null with empty
        self.finishaction(response.queue.finishaction ? response.queue.finishaction : '');

        // Disk sizes
        self.diskSpaceLeft1(response.queue.diskspace1_norm)

        // Same sizes? Then it's all 1 disk!
        if (response.queue.diskspace1 != response.queue.diskspace2) {
            self.diskSpaceLeft2(response.queue.diskspace2_norm)
        } else {
            self.diskSpaceLeft2('')
        }

        // Did we exceed the space?
        self.diskSpaceExceeded1(parseInt(response.queue.mbleft) / 1024 > parseFloat(response.queue.diskspace1))
        self.diskSpaceExceeded2(parseInt(response.queue.mbleft) / 1024 > parseFloat(response.queue.diskspace2))

        // Quota
        self.quotaLimit(response.queue.quota)
        self.quotaLimitLeft(response.queue.left_quota)

        // Cache
        self.cacheSize(response.queue.cache_size)
        self.cacheArticles(response.queue.cache_art)

        // Warnings (new warnings will trigger an update of allMessages)
        self.nrWarnings(response.queue.have_warnings)

        /***
            Spark line
        ***/
        // Break the speed if empty queue
        if (response.queue.sizeleft == '0 B') {
            response.queue.kbpersec = 0;
            response.queue.speed = '0';
        }

        // Re-format the speed
        var speedSplit = response.queue.speed.split(/\s/);
        self.speed(parseFloat(speedSplit[0]));
        self.speedMetric(speedSplit[1]);

        // Update sparkline data
        if (self.speedHistory.length >= 275) {
            // Remove first one
            self.speedHistory.shift();
        }
        // Add
        self.speedHistory.push(parseInt(response.queue.kbpersec));

        // Is sparkline visible? Not on small mobile devices..
        if ($('.sparkline-container').css('display') != 'none') {
            // Make sparkline
            if (self.speedHistory.length == 1) {
                // We only use speedhistory from SAB if we use global settings
                // Otherwise SAB doesn't know the refresh rate
                if (!self.useGlobalOptions()) {
                    sabSpeedHistory = [];
                } else {
                    // Update internally
                    self.speedHistory = sabSpeedHistory;
                }

                // Create
                $('.sparkline').peity("line", {
                    width: 275,
                    height: 32,
                    fill: '#9DDB72',
                    stroke: '#AAFFAA',
                    values: sabSpeedHistory
                })

                // Add option to open the server details tab
                $('.sparkline-container').click(function() {
                    $('a[href="#modal-options"]').trigger('click')
                    $('a[href="#options_connections"]').trigger('click')
                })

            } else {
                // Update
                $('.sparkline').text(self.speedHistory.join(",")).change()
            }
        }

        /***
            Speedlimit
        ***/
        // Nothing or 0 means 100%
        if(response.queue.speedlimit == '' || response.queue.speedlimit == '0') {
            self.speedLimitInt(100)
        } else {
            self.speedLimitInt(parseInt(response.queue.speedlimit));
        }

        // Only update from external source when user isn't doing input
        if (!$('.speedlimit-dropdown .btn-group .btn-group').is('.open')) {
            self.speedLimit(self.speedLimitInt())
        }

        /***
            Download timing and pausing
        ***/
        var timeString = response.queue.timeleft;
        if (timeString === '') {
            timeString = '0:00';
        } else {
            timeString = rewriteTime(response.queue.timeleft)
        }

        // Paused main queue
        if (self.downloadsPaused()) {
            if (response.queue.pause_int == '0') {
                timeString = glitterTranslate.paused;
            } else {
                var pauseSplit = response.queue.pause_int.split(/:/);
                var seconds = parseInt(pauseSplit[0]) * 60 + parseInt(pauseSplit[1]);
                var hours = Math.floor(seconds / 3600);
                var minutes = Math.floor((seconds -= hours * 3600) / 60);
                seconds -= minutes * 60;

                // Add leading zeros
                if (minutes < 10) minutes = '0' + minutes;
                if (seconds < 10) seconds = '0' + seconds;

                // Final formating
                timeString = glitterTranslate.paused + ' (' + rewriteTime(hours + ":" + minutes + ":" + seconds) + ')';
            }

            // Add info about amount of download (if actually downloading)
            if (response.queue.noofslots > 0 && parseInt(self.queueDataLeft()) > 0) {
                self.title(timeString + ' - ' + self.queueDataLeft() + ' ' + glitterTranslate.left + ' - SABnzbd')
            } else {
                // Set title with pause information
                self.title(timeString + ' - SABnzbd')
            }
        } else if (response.queue.noofslots > 0 && parseInt(self.queueDataLeft()) > 0) {
            // Set title only if we are actually downloading something..
            self.title(self.speedText() + ' - ' + self.queueDataLeft() + ' ' + glitterTranslate.left + ' - SABnzbd')
        } else {
            // Empty title
            self.title('SABnzbd')
        }

        // Save for timing box
        self.timeLeft(timeString);

        // Update queue rows
        self.queue.updateFromData(response.queue);
    }

    // Update history items
    self.updateHistory = function(response) {
        if (!response) return;
        self.history.updateFromData(response.history);
    }

    // Set new update timer
    self.setNextUpdate = function() {
        self.interval = setTimeout(self.refresh, parseInt(self.refreshRate()) * 1000);
    }

    // Refresh function
    self.refresh = function(forceFullHistory) {
        // Clear previous timeout to prevent double-calls
        clearTimeout(self.interval);

        // Do requests for full information
        // Catch the fail to display message
        var api_call = {
            mode: "queue",
            start: self.queue.pagination.currentStart(),
            limit: parseInt(self.queue.paginationLimit())
        }
        if (self.queue.searchTerm()) {
            parseSearchQuery(api_call, self.queue.searchTerm(), ["cat", "category", "priority"])
        }
        var queueApi = callAPI(api_call)
            .done(self.updateQueue)
            .fail(function(response) {
                // Catch the failure of authorization error
                if (response.status == 401) {
                    // Stop refresh and reload
                    clearInterval(self.interval)
                    location.reload();
                }
                // Show screen
                self.isRestarting(1)
            }).always(self.setNextUpdate);

        // Force full history update?
        if (forceFullHistory) {
            self.history.lastUpdate = 0
        }

        // Build history request and parse search
        var history_call = {
            mode: "history",
            failed_only: self.history.showFailed() * 1,
            start: self.history.pagination.currentStart(),
            limit: parseInt(self.history.paginationLimit()),
            last_history_update: self.history.lastUpdate
        }
        if (self.history.searchTerm()) {
            parseSearchQuery(history_call, self.history.searchTerm(), ["cat", "category"])
        }

        // History
        callAPI(history_call).done(self.updateHistory);

        // We are now done with any loading
        // But we wait a few ms so Knockout has time to update
        setTimeout(function() {
            self.queue.isLoading(false);
            self.history.isLoading(false);
        }, 100)

        // Return for .then() functionality
        return queueApi;
    };

    function parseSearchQuery(api_request, search, keywords) {
        var parsed_query = search_query_parse(search, { keywords: keywords })
        api_request["search"] = parsed_query.text
        for (const keyword of keywords) {
            if (Array.isArray(parsed_query[keyword])) {
                api_request[keyword] = parsed_query[keyword].join(",")
            } else {
                api_request[keyword] = parsed_query[keyword]
            }
            // Special case for priority, dirty replace of string by numeric value
            if (keyword == "priority" && api_request["priority"]) {
                for (const prio_name in self.queue.priorityName) {
                    api_request["priority"] = api_request["priority"].replace(prio_name, self.queue.priorityName[prio_name])

                }
            }
        }
    }

    // Set pause action on click of toggle
    self.pauseToggle = function() {
        callAPI({
            mode: (self.downloadsPaused() ? "resume" : "pause")
        }).then(self.refresh);
        self.downloadsPaused(!self.downloadsPaused());
    }

    // Set pause timer
    self.pauseTime = function(item, event) {
        callAPI({
            mode: 'config',
            name: 'set_pause',
            value: $(event.currentTarget).data('time')
        }).then(self.refresh);
        self.downloadsPaused(true);
    };

    // Open modal
    self.openCustomPauseTime = function() {
        // Was it loaded already?
        if (!Date.i18n) {
            jQuery.getScript('./static/javascripts/date.min.js').then(function() {
                // After loading we start again
                self.openCustomPauseTime()
            })
            return;
        }
        // Show modal
        $('#modal_custom_pause').modal('show')

        // Focus on the input field
        $('#modal_custom_pause').on('shown.bs.modal', function() {
            $('#customPauseInput').focus()
        })

        // Reset on modal close
        $('#modal_custom_pause').on('hide.bs.modal', function() {
            self.pauseCustom('');
        })
    }

    // Update on changes
    self.pauseCustom.subscribe(function(newValue) {
        // Is it plain numbers?
        if (newValue.match(/^\s*\d+\s*$/)) {
            // Treat it as a number of minutes
            newValue += "minutes";
        }

        // At least 3 charaters
        if (newValue.length < 3) {
            $('#customPauseOutput').text('').data('time', 0)
            $('#modal_custom_pause .btn-default').addClass('disabled')
            return;
        }

        // Fix DateJS bug it has some strange problem with the current day-of-month + 1
        // Removing the space makes DateJS work properly
        newValue = newValue.replace(/\s*h|\s*m|\s*d/g, function(match) {
            return match.trim()
        });

        // Parse
        var pauseParsed = Date.parse(newValue);

        // Did we get it?
        if (pauseParsed) {
            // Is it just now?
            if (pauseParsed <= Date.parse('now')) {
                // Try again with the '+' in front, the parser doesn't get 100min
                pauseParsed = Date.parse('+' + newValue);
            }

            // Calculate difference in minutes and save
            var pauseDuration = Math.round((pauseParsed - Date.parse('now')) / 1000 / 60);
            $('#customPauseOutput').html('<span class="glyphicon glyphicon-pause"></span> ' + glitterTranslate.pauseFor + ' ' + pauseDuration + ' ' + glitterTranslate.minutes)
            $('#customPauseOutput').data('time', pauseDuration)
            $('#modal_custom_pause .btn-default').removeClass('disabled')
        } else if (newValue) {
            // No..
            $('#customPauseOutput').text(glitterTranslate.pausePromptFail)
            $('#modal_custom_pause .btn-default').addClass('disabled')
        }
    })

    // Save custom pause
    self.saveCustomPause = function() {
        // Get duration
        var pauseDuration = $('#customPauseOutput').data('time');

        // If in the future
        if (pauseDuration > 0) {
            callAPI({
                mode: 'config',
                name: 'set_pause',
                value: pauseDuration
            }).then(function() {
                // Refresh and close the modal
                self.refresh()
                self.downloadsPaused(true);
                $('#modal_custom_pause').modal('hide')
            });
        }
    }

    // Update the warnings
    self.nrWarnings.subscribe(function(newValue) {
        // Really any change?
        if (newValue == self.allWarnings().length) return;

        // Get all warnings
        callAPI({
            mode: 'warnings'
        }).then(function(response) {

            // Reset it all
            self.allWarnings.removeAll();
            if (response) {
                // Newest first
                response.warnings.reverse()

                // Go over all warnings and add
                $.each(response.warnings, function(index, warning) {
                    // Reformat CSS label and date
                    // Replaces spaces by non-breakable spaces and newlines with br's
                    var warningData = {
                        index: index,
                        type: glitterTranslate.status[warning.type].slice(0, -1),
                        text: convertHTMLtoText(warning.text).replace(/ /g, '\u00A0').replace(/(?:\r\n|\r|\n)/g, '<br />'),
                        timestamp: warning.time,
                        css: (warning.type == "ERROR" ? "danger" : warning.type == "WARNING" ? "warning" : "info"),
                        clear: self.clearWarnings
                    };
                    self.allWarnings.push(warningData)
                })
            }
        });
    })

    // Clear warnings
    self.clearWarnings = function() {
        callAPI({
            mode: "warnings",
            name: "clear"
        }).done(self.refresh)
    }

    // Clear messages
    self.clearMessages = function(whatToRemove) {
        // Remove specifc type of messages
        self.allMessages.remove(function(item) { return item.index == whatToRemove });
        // Now so we don't show again today
        localStorageSetItem(whatToRemove, Date.now())
    }

    // Update on speed-limit change
    self.speedLimit.subscribe(function(newValue) {
        // Only on new load
        if (!self.speedLimitInt()) return;

        // Update
        if (self.speedLimitInt() != newValue) {
            callAPI({
                mode: "config",
                name: "speedlimit",
                value: newValue
            })
        }
    });

    // Clear speedlimit
    self.clearSpeedLimit = function() {
        // Send call to override speedlimit
        callAPI({
            mode: "config",
            name: "speedlimit",
            value: 100
        })
        self.speedLimitInt(100.0)
        self.speedLimit(100.0)
    }

    // Shutdown options
    self.setOnQueueFinish = function(model, event) {
        // Something changes
        callAPI({
            mode: 'queue',
            name: 'change_complete_action',
            value: $(event.target).val()
        })
    }

    // Use global settings or device-specific?
    self.useGlobalOptions.subscribe(function(newValue) {
        // Reload in case of enabling global options
        if (newValue) document.location = document.location;
    })

    // Update refreshrate
    self.refreshRate.subscribe(function(newValue) {
        // Refresh now
        self.refresh();

        // Save in config if global-settings
        if (self.useGlobalOptions()) {
            callAPI({
                mode: "set_config",
                section: "misc",
                keyword: "refresh_rate",
                value: newValue
            })
        }
    })

    /***
         Add NZB's
    ***/
    // Updating the label
    self.updateBrowseLabel = function(data, event) {
        // Get filename
        var fileName = $(event.target).val().replace(/\\/g, '/').replace(/.*\//, '');
        // Set label
        if (fileName) $('.btn-file em').text(fileName)
    }

    // Add NZB form
    self.addNZB = function(form) {
        // Anything?
        if (!$(form.nzbFile)[0].files[0] && !$(form.nzbURL).val()) {
            $('.btn-file, input[name="nzbURL"]').attr('style', 'border-color: red !important')
            setTimeout(function() { $('.btn-file, input[name="nzbURL"]').css('border-color', '') }, 2000)
            return false;
        }

        // Upload file using the method we also use for drag-and-drop
        if ($(form.nzbFile)[0].files[0]) {
            self.addNZBFromFile($(form.nzbFile)[0].files);
            // Hide modal, upload will reset the form
            $("#modal-add-nzb").modal("hide");
        } else if ($(form.nzbURL).val()) {
            // Or add URL
            var theCall = {
                mode: "addurl",
                name: $(form.nzbURL).val(),
                nzbname: $('#nzbname').val(),
                password: $('#password').val(),
                script: $('#modal-add-nzb select[name="Post-processing"]').val(),
                priority: $('#modal-add-nzb select[name="Priority"]').val(),
                pp: $('#modal-add-nzb select[name="Processing"]').val()
            }

            // Optional, otherwise they get mis-labeled if left empty
            if ($('#modal-add-nzb select[name="Category"]').val() != '*') theCall.cat = $('#modal-add-nzb select[name="Category"]').val()
            if ($('#modal-add-nzb select[name="Processing"]').val()) theCall.pp = $('#modal-add-nzb select[name="Category"]').val()

            // Add
            callAPI(theCall).then(function(r) {
                // Hide and reset/refresh
                self.refresh()
                $("#modal-add-nzb").modal("hide");
                form.reset()
                $('#nzbname').val('')
            });
        }
    }

    // default to url input when modal is shown
    $('#modal-add-nzb').on('shown.bs.modal', function() {
      $('input[name="nzbURL"]').focus();
    })

    // From the upload or filedrop
    self.addNZBFromFile = function(files, fileindex) {
        // First file
        if (fileindex === undefined) {
            fileindex = 0
        }
        var file = files[fileindex]
        fileindex++

        // Check if it's maybe a folder, we can't handle those
        if (!file.type && file.size % 4096 == 0) return;

        // Add notification
        showNotification('.main-notification-box-uploading', 0, fileindex)

        // Adding a file happens through this special function
        var data = new FormData();
        data.append("name", file);
        data.append("mode", "addfile");
        data.append("nzbname", $('#nzbname').val());
        data.append("password", $('#password').val());
        data.append("script", $('#modal-add-nzb select[name="Post-processing"]').val())
        data.append("priority", $('#modal-add-nzb select[name="Priority"]').val())
        data.append("apikey", apiKey);

        // Optional, otherwise they get mis-labeled if left empty
        if ($('#modal-add-nzb select[name="Category"]').val() != '*') data.append("cat", $('#modal-add-nzb select[name="Category"]').val());
        if ($('#modal-add-nzb select[name="Processing"]').val()) data.append("pp", $('#modal-add-nzb select[name="Processing"]').val());

        // Add this one
        $.ajax({
            url: "./api",
            type: "POST",
            cache: false,
            processData: false,
            contentType: false,
            data: data
        }).then(function(r) {
            // Are we done?
            if (fileindex < files.length) {
                // Do the next one
                self.addNZBFromFile(files, fileindex)
            } else {
                // Refresh
                self.refresh();
                // Hide notification
                hideNotification()
                // Reset the form
                $('#modal-add-nzb form').trigger('reset');
                $('#nzbname').val('')
                $('.btn-file em').html(glitterTranslate.chooseFile + '&hellip;')
            }
        });
    }

    // Load status info
    self.loadStatusInfo = function(item, event) {
        // Full refresh? Only on click and for the status-screen
        var statusFullRefresh = (event != undefined) && $('#options-status').hasClass('active');

        // Measure performance? Takes a while
        var statusPerformance = (event != undefined) && $(event.currentTarget).hasClass('diskspeed-button');

        // Make it spin if the user requested it otherwise we don't,
        // because browsers use a lot of CPU for the animation
        if (statusFullRefresh) {
            self.hasStatusInfo(false)
        }

        // Show loading text for performance measures
        if (statusPerformance) {
            self.hasPerformanceInfo(false)
        }

        // Load the custom status info, allowing for longer timeouts
        callAPI({
            mode: 'status',
            skip_dashboard: (!statusFullRefresh) * 1,
            calculate_performance: statusPerformance * 1,
        }, 30000).then(function(data) {
            // Update basic
            self.statusInfo.folders(data.status.folders)
            self.statusInfo.loadavg(data.status.loadavg)
            self.statusInfo.delayed_assembler(data.status.delayed_assembler)

            // Update the full set if the data is available
            if ("dnslookup" in data.status) {
                self.statusInfo.pystone(data.status.pystone)
                self.statusInfo.downloaddir(data.status.downloaddir)
                self.statusInfo.downloaddirspeed(data.status.downloaddirspeed)
                self.statusInfo.completedir(data.status.completedir)
                self.statusInfo.completedirspeed(data.status.completedirspeed)
                self.statusInfo.internetbandwidth(data.status.internetbandwidth)
                self.statusInfo.dnslookup(data.status.dnslookup)
                self.statusInfo.active_socks5_proxy(data.status.active_socks5_proxy)
                self.statusInfo.localipv4(data.status.localipv4)
                self.statusInfo.publicipv4(data.status.publicipv4)
                self.statusInfo.ipv6(data.status.ipv6 || glitterTranslate.noneText)
            }

            // Update the servers
            if (self.statusInfo.servers().length != data.status.servers.length) {
                // Empty them, in case of update
                self.statusInfo.servers([])

                // Initial add
                $.each(data.status.servers, function() {
                    self.statusInfo.servers.push({
                        'servername': ko.observable(this.servername),
                        'serveroptional': ko.observable(this.serveroptional),
                        'serverpriority': ko.observable(this.serverpriority),
                        'servertotalconn': ko.observable(this.servertotalconn),
                        'serverssl': ko.observable(this.serverssl),
                        'serversslinfo': ko.observable(this.serversslinfo),
                        'serveractiveconn': ko.observable(this.serveractiveconn),
                        'servererror': ko.observable(this.servererror),
                        'serveractive': ko.observable(this.serveractive),
                        'serverconnections': ko.observableArray(this.serverconnections),
                        'serverbps': ko.observable(this.serverbps)
                    })
                })
            } else {
                // Update
                $.each(data.status.servers, function(index) {
                    var activeServer = self.statusInfo.servers()[index];
                    activeServer.servername(this.servername),
                        activeServer.serveroptional(this.serveroptional),
                        activeServer.serverpriority(this.serverpriority),
                        activeServer.servertotalconn(this.servertotalconn),
                        activeServer.serverssl(this.serverssl),
                        activeServer.serversslinfo(this.serversslinfo),
                        activeServer.serveractiveconn(this.serveractiveconn),
                        activeServer.servererror(this.servererror),
                        activeServer.serveractive(this.serveractive),
                        activeServer.serverconnections(this.serverconnections),
                        activeServer.serverbps(this.serverbps)
                })
            }

            // Add tooltips to possible new items
            if (!isMobile) $('#modal-options [data-tooltip="true"]').tooltip({ trigger: 'hover', container: 'body' })

            // Stop it spin
            self.hasStatusInfo(true)
            self.hasPerformanceInfo(true)
        });
    }

    // Download a test-NZB
    self.testDownload = function(data, event) {
        var nzbSize = $(event.target).data('size')

        // Maybe it was a click on the icon?
        if (nzbSize == undefined) {
            nzbSize = $(event.target.parentElement).data('size')
        }

        // Build request
        var theCall = {
            mode: "addurl",
            name: "https://sabnzbd.org/tests/test_download_" + nzbSize + ".nzb",
            priority: self.queue.priorityName["Force"]
        }

        // Add
        callAPI(theCall).then(function(r) {
            // Hide and reset/refresh
            self.refresh()
            $("#modal-options").modal("hide");
        });
    }

    // Unblock server
    self.unblockServer = function(servername) {
        callAPI({
            mode: "status",
            name: "unblock_server",
            value: servername
        }).then(function() {
            $("#modal-options").modal("hide");
        })
    }

    // Refresh connections page
    var connectionRefresh
    $('.nav-tabs a[href="#options_connections"]').on('shown.bs.tab', function() {
        // Check size on open
        checkSize()

        // Set the interval
        connectionRefresh = setInterval(function() {
            // Start small
            checkSize()

            // Check if still visible
            if (!$('#options_connections').is(':visible') && connectionRefresh) {
                // Stop refreshing
                clearInterval(connectionRefresh)
                return
            }
            // Update the server stats (speed/connections)
            self.loadStatusInfo()

        }, self.refreshRate() * 1000)
    })

    // On close of the tab
    $('.nav-tabs a[href="#options_connections"]').on('hidden.bs.tab', function() {
        checkSize()
    })

    // Function that handles the actual sizing of connections tab
    function checkSize() {
        // Any connections?
        if (self.showActiveConnections() && $('#options_connections').is(':visible') && $('.table-server-connections').height() > 1) {
            var mainWidth = $('.main-content').width()
            $('#modal-options .modal-dialog').width(mainWidth * 0.85 > 650 ? mainWidth * 0.85 : '')
        } else {
            // Small again
            $('#modal-options .modal-dialog').width('')
        }
    }

    // Make sure Connections get refreshed also after open->close->open
    $('#modal-options').on('show.bs.modal', function() {
        // Trigger
        $('.nav-tabs a[href="#options_connections"]').trigger('shown.bs.tab')
    })

    // Orphaned folder processing
    self.folderProcess = function(folder, htmlElement) {
        // Hide tooltips (otherwise they stay forever..)
        $('#options-orphans [data-tooltip="true"]').tooltip('hide')

        // Show notification on delete
        if ($(htmlElement.currentTarget).data('action') == 'delete_orphan') {
            showNotification('.main-notification-box-removing', 1000)
        } else {
            // Adding back to queue
            showNotification('.main-notification-box-sendback', 2000)
        }

        // Activate
        callAPI({
            mode: "status",
            name: $(htmlElement.currentTarget).data('action'),
            value: $("<div/>").html(folder).text()
        }).then(function() {
            // Refresh
            self.loadStatusInfo(true, true)
            // Hide notification
            hideNotification()
        })
    }

    // Orphaned folder deletion of all
    self.removeAllOrphaned = function() {
        if (!self.confirmDeleteHistory() || confirm(glitterTranslate.clearWarn)) {
            // Show notification
            showNotification('.main-notification-box-removing-multiple', 0, self.statusInfo.folders().length)
            // Delete them all
            callAPI({
                mode: "status",
                name: "delete_all_orphan"
            }).then(function() {
                // Remove notifcation and update screen
                hideNotification()
                self.loadStatusInfo(true, true)
            })
        }
    }

    // Orphaned folder adding of all
    self.addAllOrphaned = function() {
        if (!self.confirmDeleteHistory() || confirm(glitterTranslate.clearWarn)) {
            // Show notification
            showNotification('.main-notification-box-sendback')
            // Delete them all
            callAPI({
                mode: "status",
                name: "add_all_orphan"
            }).then(function() {
                // Remove notifcation and update screen
                hideNotification()
                self.loadStatusInfo(true, true)
            })
        }
    }

    // Toggle Glitter's compact layout dynamically
    self.displayCompact.subscribe(function() {
        $('body').toggleClass('container-compact')
    })

    // Toggle full width
    self.displayFullWidth.subscribe(function() {
        $('body').toggleClass('container-full-width')
    })

    // Toggle Glitter's tabbed modus
    self.displayTabbed.subscribe(function() {
        $('body').toggleClass('container-tabbed')
    })

    // Change hash for page-reload
    $('.history-queue-swicher .nav-tabs a').on('shown.bs.tab', function(e) {
        window.location.hash = e.target.hash;
    })

    /**
         SABnzb options
    **/
    // Shutdown
    self.shutdownSAB = function() {
        if (confirm(glitterTranslate.shutdown)) {
            // Show notification and return true to follow the URL
            showNotification('.main-notification-box-shutdown')
            return true
        }
    }
    // Restart
    self.restartSAB = function() {
        if (!confirm(glitterTranslate.restart)) return;
        // Call restart function
        callAPI({ mode: "restart" })

        // Set counter, we need at least 15 seconds
        self.isRestarting(Math.max(1, Math.floor(15 / self.refreshRate())));
        // Force refresh in case of very long refresh-times
        if (self.refreshRate() > 30) {
            setTimeout(self.refresh, 30 * 1000)
        }
    }
    // Queue actions
    self.doQueueAction = function(data, event) {
        // Event
        var theAction = $(event.target).data('mode');
        // Show notification if available
        if (['rss_now', 'watched_now'].indexOf(theAction) > -1) {
            showNotification('.main-notification-box-' + theAction, 2000)
        }
        // Send to the API
        callAPI({ mode: theAction })
    }
    // Repair queue
    self.repairQueue = function() {
        if (!confirm(glitterTranslate.repair)) return;
        // Hide the modal and show the notifucation
        $("#modal-options").modal("hide");
        showNotification('.main-notification-box-queue-repair', 5000)
        // Call the API
        callAPI({ mode: "restart_repair" })
    }
    // Force disconnect
    self.forceDisconnect = function() {
        // Show notification
        showNotification('.main-notification-box-disconnect', 3000)
        // Call API
        callAPI({ mode: "disconnect" }).then(function() {
            $("#modal-options").modal("hide");
        })
    }

    /***
        Retrieve config information and do startup functions
    ***/
    // Force compact mode as fast as possible
    if (localStorageGetItem('displayCompact') === 'true') {
        // Add extra class
        $('body').addClass('container-compact')
    }

    if (localStorageGetItem('displayFullWidth') === 'true') {
        // Add extra class
        $('body').addClass('container-full-width')
    }

    // Tabbed layout?
    if (localStorageGetItem('displayTabbed') === 'true') {
        $('body').addClass('container-tabbed')

        var tab_from_hash = location.hash.replace(/^#/, '');
        if (tab_from_hash) {
            $('.history-queue-swicher .nav-tabs a[href="#' + tab_from_hash + '"]').tab('show');
        }
    }

    self.globalInterfaceSettings = [
        'dateFormat',
        'extraQueueColumns',
        'extraHistoryColumns',
        'displayCompact',
        'displayFullWidth',
        'displayTabbed',
        'confirmDeleteQueue',
        'confirmDeleteHistory',
        'keyboardShortcuts'
    ]

    // Save the rest in config if global-settings
    var saveInterfaceSettings = function(newValue) {
        var interfaceSettings = {}
        for (const setting of self.globalInterfaceSettings) {
            interfaceSettings[setting] = self[setting]
        }
        callAPI({
            mode: "set_config",
            section: "misc",
            keyword: "interface_settings",
            value: ko.toJSON(interfaceSettings)
        })
    }

    // Get the speed-limit, refresh rate and server names
    callAPI({
        mode: 'get_config'
    }).then(function(response) {
        // Do we use global, or local settings?
        if (self.useGlobalOptions()) {
            // Set refreshrate (defaults to 1/s)
            if (!response.config.misc.refresh_rate) response.config.misc.refresh_rate = 1;
            self.refreshRate(response.config.misc.refresh_rate.toString());

            // Set history and queue limit
            self.history.paginationLimit(response.config.misc.history_limit.toString())
            self.queue.paginationLimit(response.config.misc.queue_limit.toString())

            // Import the rest of the settings
            if (response.config.misc.interface_settings) {
                var interfaceSettings = JSON.parse(response.config.misc.interface_settings);
                for (const setting of self.globalInterfaceSettings) {
                    if (setting in interfaceSettings) {
                        self[setting](interfaceSettings[setting]);
                    }
                }
            }
            // Only subscribe now to prevent collisions between localStorage and config settings updates
            for (const setting of self.globalInterfaceSettings) {
                self[setting].subscribe(saveInterfaceSettings);
            }
        }

        // Set bandwidth limit
        if (!response.config.misc.bandwidth_max) response.config.misc.bandwidth_max = false;
        self.bandwithLimit(response.config.misc.bandwidth_max);

        // Reformat and set categories
        self.queue.categoriesList($.map(response.config.categories, function(cat) {
            // Default?
            if(cat.name == '*') return { catValue: '*', catText: glitterTranslate.defaultText };
            return { catValue: cat.name, catText: cat.name };
        }))

        // Get the scripts, if there are any
        if(response.config.misc.script_dir) {
            callAPI({
                mode: 'get_scripts'
            }).then(function(script_response) {
                // Reformat script-list
                self.queue.scriptsList($.map(script_response.scripts, function(script) {
                    // None?
                    if(script == 'None') return { scriptValue: 'None', scriptText: glitterTranslate.noneText };
                    return { scriptValue: script, scriptText: script };
                }))
                self.queue.scriptsListLoaded(true)
            })
        } else {
            // We can already continue
            self.queue.scriptsListLoaded(true)
        }


        // Already set if we are using a proxy
        if (response.config.misc.socks5_proxy_url) self.statusInfo.active_socks5_proxy(true)

        // Set logging and only then subscribe to changes
        self.loglevel(response.config.logging.log_level);
        self.loglevel.subscribe(function(newValue) {
            callAPI({
                mode: "set_config",
                section: "logging",
                keyword: "log_level",
                value: newValue
            });
        })

        // Update message
        if (newRelease) {
            self.allMessages.push({
                index: 'UpdateMsg',
                type: glitterTranslate.status['INFO'],
                text: ('<a class="queue-update-sab" href="' + newReleaseUrl + '" target="_blank">' + glitterTranslate.updateAvailable + ' ' + newRelease + ' <span class="glyphicon glyphicon-save"></span></a>'),
                css: 'info'
            });
        }

        // Message about cache - Not for 5 days if user ignored it
        if (!response.config.misc.cache_limit && localStorageGetItem('CacheMsg') * 1 + (1000 * 3600 * 24 * 5) < Date.now()) {
            self.allMessages.push({
                index: 'CacheMsg',
                type: glitterTranslate.status['INFO'],
                text: ('<a href="./config/general/#cache_limit">' + glitterTranslate.useCache.replace(/<br \/>/g, " ") + ' <span class="glyphicon glyphicon-cog"></span></a>'),
                css: 'info',
                clear: function() { self.clearMessages('CacheMsg') }
            });
        }

        // Message about tips and tricks, only once
        if (response.config.misc.notified_new_skin < 2) {
            self.allMessages.push({
                index: 'TipsMsgV110',
                type: glitterTranslate.status['INFO'],
                text: glitterTranslate.glitterTips + ' <a class="queue-update-sab" href="https://sabnzbd.org/wiki/extra/glitter-tips-and-tricks" target="_blank">Glitter Tips and Tricks <span class="glyphicon glyphicon-new-window"></span></a>',
                css: 'info',
                clear: function() {
                    // Update the config to not show again
                    callAPI({
                        mode: 'set_config',
                        section: 'misc',
                        keyword: 'notified_new_skin',
                        value: 2
                    })

                    // Remove the actual message
                    self.clearMessages('TipsMsgV110')
                }
            });
        }
    })

    // Orphaned folder check - Not for 5 days if user ignored it
    var orphanMsg = localStorageGetItem('OrphanedMsg') * 1 + (1000 * 3600 * 24 * 5) < Date.now();
    // Delay the check
    if (orphanMsg) {
        setTimeout(self.loadStatusInfo, 200);
    }

    // On any status load we check Orphaned folders
    self.hasStatusInfo.subscribe(function(finishedLoading) {
        // Loaded or just starting?
        if (!finishedLoading) return;

        // Orphaned folders? If user clicked away we check again in 5 days
        if (self.statusInfo.folders().length >= 3 && orphanMsg) {
            // Check if not already there
            if (!ko.utils.arrayFirst(self.allMessages(), function(item) { return item.index == 'OrphanedMsg' })) {
                self.allMessages.push({
                    index: 'OrphanedMsg',
                    type: glitterTranslate.status['INFO'],
                    text: glitterTranslate.orphanedJobsMsg + ' <a href="#" onclick="showOrphans()"><span class="glyphicon glyphicon-wrench"></span></a>',
                    css: 'info',
                    clear: function() { self.clearMessages('OrphanedMsg') }
                });
            }
        } else {
            // Remove any message, if it was there
            self.allMessages.remove(function(item) {
                return item.index == 'OrphanedMsg';
            })
        }
    })

    // Message about localStorage not being enabled every 20 days
    if (!hasLocalStorage && localStorageGetItem('LocalStorageMsg') * 1 + (1000 * 3600 * 24 * 20) < Date.now()) {
        self.allMessages.push({
            index: 'LocalStorageMsg',
            type: glitterTranslate.status['WARNING'].replace(':', ''),
            text: glitterTranslate.noLocalStorage,
            css: 'warning',
            clear: function() { self.clearMessages('LocalStorageMsg') }
        });
    }

    if (self.keyboardShortcuts()) {
        $(document).bind('keydown', 'p', function(e) {
            self.pauseToggle();
        });
        $(document).bind('keydown', 'a', function(e) {
            // avoid modal clashes
            if (!$('.modal-dialog').is(':visible')) {
                $('#modal-add-nzb').modal('show');
            }
        });
        $(document).bind('keydown', 'c', function(e) {
            window.location.href = './config/';
        });
        $(document).bind('keydown', 's', function(e) {
            // Update the data
            self.loadStatusInfo(true, true)
            // avoid modal clashes
            if (!$('.modal-dialog').is(':visible')) {
                $('#modal-options').modal('show');
            }
        });
        $(document).bind('keydown', 'shift+left', function(e) {
            if($("body").hasClass("container-tabbed")) {
                $('#history-tab.active > ul.pagination li.active').prev().click();
                $('#queue-tab.active > ul.pagination li.active').prev().click();
            } else {
                $('#history-tab > ul.pagination li.active').prev().click();
                $('#queue-tab > ul.pagination li.active').prev().click();
            }
            e.preventDefault();
        });
        $(document).bind('keydown', 'shift+right', function(e) {
            if($("body").hasClass("container-tabbed")) {
                $('#history-tab.active > ul.pagination li.active').next().click();
                $('#queue-tab.active > ul.pagination li.active').next().click();
            } else {
                $('#history-tab > ul.pagination li.active').next().click();
                $('#queue-tab > ul.pagination li.active').next().click();
            }
            e.preventDefault();
        });
        $(document).bind('keydown', 'shift+up', function(e) {
            if($("body").hasClass("container-tabbed")) {
                $('#history-tab.active > ul.pagination li').first().click();
                $('#queue-tab.active > ul.pagination li').first().click();
            } else {
                $('#history-tab > ul.pagination li').first().click();
                $('#queue-tab > ul.pagination li').first().click();
            }
            e.preventDefault();
        });
        $(document).bind('keydown', 'shift+down', function(e) {
            if($("body").hasClass("container-tabbed")) {
                $('#history-tab.active > ul.pagination li').last().click();
                $('#queue-tab.active > ul.pagination li').last().click();
            } else {
                $('#history-tab > ul.pagination li').last().click();
                $('#queue-tab > ul.pagination li').last().click();
            }
            e.preventDefault();
        });
    }

    /***
        Date-stuff
    ***/
    moment.locale(displayLang);

    // Fill the basic info for date-formats with current date-time
    $('[name="general-date-format"] option').each(function() {
        $(this).text(displayDateTime('', $(this).val()), '')
    })

    // Update the date every minute
    setInterval(function() {
        $('[data-timestamp]').each(function() {
            $(this).text(displayDateTime($(this).data('timestamp'), self.dateFormat(), 'X'))
        })
    }, 60 * 1000)

    /***
        End of main functions, start of the fun!
    ***/
    // Trigger first refresh
    self.interval = setTimeout(self.refresh, parseInt(self.refreshRate()) * 1000);

    // And refresh now!
    self.refresh()

    // Special options for (non) mobile
    if (isMobile) {
        // Disable accept parameter on file inputs, as it doesn't work on mobile Safari
        $("input[accept!=''][accept]").attr("accept","")
    } else {
        // Activate tooltips
        $('[data-tooltip="true"]').tooltip({ trigger: 'hover', container: 'body' })
    }
}

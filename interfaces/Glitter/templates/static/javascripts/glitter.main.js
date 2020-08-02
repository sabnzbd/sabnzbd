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
    self.confirmDeleteQueue = ko.observable(true).extend({ persist: 'confirmDeleteQueue' });
    self.confirmDeleteHistory = ko.observable(true).extend({ persist: 'confirmDeleteHistory' });
    self.extraQueueColumn = ko.observable('').extend({ persist: 'extraColumn' });
    self.extraHistoryColumn = ko.observable('').extend({ persist: 'extraHistoryColumn' });
    self.showActiveConnections = ko.observable(false).extend({ persist: 'showActiveConnections' });
    self.speedMetrics = { K: "KB/s", M: "MB/s", G: "GB/s" };

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
    self.nrWarnings = ko.observable(0);
    self.allWarnings = ko.observableArray([]);
    self.allMessages = ko.observableArray([]);
    self.onQueueFinish = ko.observable('');
    self.speedHistory = [];

    // Statusinfo container
    self.hasStatusInfo = ko.observable(false);
    self.hasPerformanceInfo = ko.observable(false);
    self.statusInfo = {};
    self.statusInfo.folders = ko.observableArray([]);
    self.statusInfo.servers = ko.observableArray([]);
    self.statusInfo.localipv4 = ko.observable();
    self.statusInfo.publicipv4 = ko.observable();
    self.statusInfo.ipv6 = ko.observable();
    self.statusInfo.dnslookup = ko.observable();
    self.statusInfo.pystone = ko.observable();
    self.statusInfo.cpumodel = ko.observable();
    self.statusInfo.loglevel = ko.observable();
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
        if(!self.bandwithLimit()) return;

        // The text
        var bandwithLimitText = self.bandwithLimit().replace(/[^a-zA-Z]+/g, '');

        // Only the number
        var speedLimitNumberFull = (parseFloat(self.bandwithLimit()) * (self.speedLimit() / 100));

        // Trick to only get decimal-point when needed
        var speedLimitNumber = Math.round(speedLimitNumberFull*10)/10;

        // Fix it for lower than 1MB/s
        if(bandwithLimitText == 'M' && speedLimitNumber < 1) {
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
        if(self.downloadsPaused()) {
            return './staticcfg/ico/faviconpaused.ico?v=1.1.0';
        } else {
            return './staticcfg/ico/favicon.ico?v=1.1.0';
        }
    })

    // Dynamic queue length check
    self.hasQueue = ko.pureComputed(function() {
        return(self.queue.queueItems().length > 0 || self.queue.searchTerm() || self.queue.isLoading())
    })

    // Dynamic history length check
    self.hasHistory = ko.pureComputed(function() {
        // We also 'have history' if we can't find any results of the search or there are no failed ones
        return (self.history.historyItems().length > 0 || self.history.searchTerm() || self.history.showFailed() || self.history.isLoading())
    })

    self.hasWarnings = ko.pureComputed(function() {
        return(self.allWarnings().length > 0)
    })

    // Check for any warnings/messages
    self.hasMessages = ko.pureComputed(function() {
        return parseInt(self.nrWarnings()) + self.allMessages().length;
    })

    // Update main queue
    self.updateQueue = function(response) {
        // Block in case off dragging
        if(!self.queue.shouldUpdate()) return;

        // Make sure we are displaying the interface
        if(self.isRestarting() >= 1) {
            // Decrease the counter by 1
            // In case of restart (which takes time to fire) we count down
            // In case of re-connect after failure it counts from 1 so emmediate continuation
            self.isRestarting(self.isRestarting() - 1);
            return;
        }

        /***
            Possible login failure?
        ***/
        if(response.hasOwnProperty('error') && response.error == 'Missing authentication') {
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
        self.onQueueFinish(response.queue.finishaction ? response.queue.finishaction : '');

        // Disk sizes
        self.diskSpaceLeft1(response.queue.diskspace1_norm)

        // Same sizes? Then it's all 1 disk!
        if(response.queue.diskspace1 != response.queue.diskspace2) {
            self.diskSpaceLeft2(response.queue.diskspace2_norm)
        } else {
            self.diskSpaceLeft2('')
        }

        // Did we exceed the space?
        self.diskSpaceExceeded1(parseInt(response.queue.mbleft)/1024 > parseFloat(response.queue.diskspace1))
        self.diskSpaceExceeded2(parseInt(response.queue.mbleft)/1024 > parseFloat(response.queue.diskspace2))

        // Quota
        self.quotaLimit(response.queue.quota)
        self.quotaLimitLeft(response.queue.left_quota)

        // System load
        self.systemLoad(response.queue.loadavg)

        // Cache
        self.cacheSize(response.queue.cache_size)
        self.cacheArticles(response.queue.cache_art)

        // Warnings (new warnings will trigger an update of allMessages)
        self.nrWarnings(response.queue.have_warnings)

        /***
            Spark line
        ***/
        // Break the speed if empty queue
        if(response.queue.sizeleft == '0 B') {
            response.queue.kbpersec = 0;
            response.queue.speed = '0';
        }

        // Re-format the speed
        var speedSplit = response.queue.speed.split(/\s/);
        self.speed(parseFloat(speedSplit[0]));
        self.speedMetric(speedSplit[1]);

        // Update sparkline data
        if(self.speedHistory.length >= 275) {
            // Remove first one
            self.speedHistory.shift();
        }
        // Add
        self.speedHistory.push(parseInt(response.queue.kbpersec));

        // Is sparkline visible? Not on small mobile devices..
        if($('.sparkline-container').css('display') != 'none') {
            // Make sparkline
            if(self.speedHistory.length == 1) {
                // We only use speedhistory from SAB if we use global settings
                // Otherwise SAB doesn't know the refresh rate
                if(!self.useGlobalOptions()) {
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

            } else {
                // Update
                $('.sparkline').text(self.speedHistory.join(",")).change()
            }
        }

        /***
            Speedlimit
        ***/
        // Nothing = 100%
        response.queue.speedlimit = (response.queue.speedlimit == '') ? 100.0 : parseFloat(response.queue.speedlimit).toFixed(1);
        // Trick to only get decimal-point when needed
        response.queue.speedlimit = Math.round(response.queue.speedlimit*10)/10;
        self.speedLimitInt(response.queue.speedlimit)

        // Only update from external source when user isn't doing input
        if(!$('.speedlimit-dropdown .btn-group .btn-group').is('.open')) {
            self.speedLimit(response.queue.speedlimit)
        }

        /***
            Download timing and pausing
        ***/
        var timeString = response.queue.timeleft;
        if(timeString === '') {
            timeString = '0:00';
        } else {
            timeString = rewriteTime(response.queue.timeleft)
        }

        // Paused main queue
        if(self.downloadsPaused()) {
            if(response.queue.pause_int == '0') {
                timeString = glitterTranslate.paused;
            } else {
                var pauseSplit = response.queue.pause_int.split(/:/);
                var seconds = parseInt(pauseSplit[0]) * 60 + parseInt(pauseSplit[1]);
                var hours = Math.floor(seconds / 3600);
                var minutes = Math.floor((seconds -= hours * 3600) / 60);
                seconds -= minutes * 60;

                // Add leading zeros
                if(minutes < 10) minutes = '0' + minutes;
                if(seconds < 10) seconds = '0' + seconds;

                // Final formating
                timeString = glitterTranslate.paused + ' (' + rewriteTime(hours + ":" + minutes + ":" + seconds) + ')';
            }

            // Add info about amount of download (if actually downloading)
            if(response.queue.noofslots > 0 && parseInt(self.queueDataLeft()) > 0) {
                self.title(timeString + ' - ' + self.queueDataLeft() + ' ' + glitterTranslate.left + ' - SABnzbd')
            } else {
                // Set title with pause information
                self.title(timeString + ' - SABnzbd')
            }
        } else if(response.queue.noofslots > 0 && parseInt(self.queueDataLeft()) > 0) {
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
        if(!response) return;
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

        /**
            Limited refresh
        **/
        // Only update the title when page not visible
        if(!pageIsVisible) {
            // Request new title
            callSpecialAPI('./queue/', { limit: 1, start: 0 }).done(function(data) {
                // Split title & speed
                var dataSplit = data.split('|||');

                // Maybe the result is actually the login page?
                if(dataSplit[0].substring(0, 11) === '<html lang=') {
                    // Redirect
                    document.location = document.location
                    return
                }

                // Set title
                self.title(dataSplit[0]);

                // Update sparkline data
                if(self.speedHistory.length >= 50) {
                    // Remove first one
                    self.speedHistory.shift();
                }
                // Add
                self.speedHistory.push(dataSplit[1]);

                // Does it contain 'Paused'? Update icon!
                self.downloadsPaused(data.indexOf(glitterTranslate.paused) > -1)

                // Force the next full update to be full
                self.history.lastUpdate = 0
            }).always(self.setNextUpdate)
            // Do not continue!
            return;
        }

        /**
            Full refresh
        **/
        // Do requests for full information
        // Catch the fail to display message
        var queueApi = callAPI({
            mode: "queue",
            search: self.queue.searchTerm(),
            start: self.queue.pagination.currentStart(),
            limit: parseInt(self.queue.paginationLimit())
        })
        .done(self.updateQueue)
        .fail(function(response) {
            // Catch the failure of authorization error
            if(response.status == 401) {
                // Stop refresh and reload
                clearInterval(self.interval)
                location.reload();
            }
            // Show screen
            self.isRestarting(1)
        }).always(self.setNextUpdate);

        // Force full history update?
        if(forceFullHistory) {
            self.history.lastUpdate = 0
        }

        // History
        callAPI({
            mode: "history",
            search: self.history.searchTerm(),
            failed_only: self.history.showFailed()*1,
            start: self.history.pagination.currentStart(),
            limit: parseInt(self.history.paginationLimit()),
            last_history_update: self.history.lastUpdate
        }).done(self.updateHistory);

        // We are now done with any loading
        // But we wait a few ms so Knockout has time to update
        setTimeout(function() {
            self.queue.isLoading(false);
            self.history.isLoading(false);
        }, 100)

        // Return for .then() functionality
        return queueApi;
    };

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
        if(!Date.i18n) {
             jQuery.getScript('./static/javascripts/date.min.js').then(function() {
                // After loading we start again
                self.openCustomPauseTime()
             })
             return;
        }
        // Show modal
        $('#modal_custom_pause').modal('show')

        // Focus on the input field
        $('#modal_custom_pause').on('shown.bs.modal', function () {
            $('#customPauseInput').focus()
        })

        // Reset on modal close
        $('#modal_custom_pause').on('hide.bs.modal', function () {
            self.pauseCustom('');
        })
    }

    // Update on changes
    self.pauseCustom.subscribe(function(newValue) {
        // Is it plain numbers?
        if(newValue.match(/^\s*\d+\s*$/)) {
            // Treat it as a number of minutes
            newValue += "minutes";
        }

        // At least 3 charaters
        if(newValue.length < 3) {
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
        if(pauseParsed) {
            // Is it just now?
            if(pauseParsed <= Date.parse('now')) {
                // Try again with the '+' in front, the parser doesn't get 100min
                pauseParsed = Date.parse('+' + newValue);
            }

            // Calculate difference in minutes and save
            var pauseDuration = Math.round((pauseParsed - Date.parse('now'))/1000/60);
            $('#customPauseOutput').html('<span class="glyphicon glyphicon-pause"></span> ' +glitterTranslate.pauseFor + ' ' + pauseDuration + ' ' + glitterTranslate.minutes)
            $('#customPauseOutput').data('time', pauseDuration)
            $('#modal_custom_pause .btn-default').removeClass('disabled')
        } else if(newValue) {
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
        if(pauseDuration > 0) {
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
        if(newValue == self.allWarnings().length) return;

        // Get all warnings
        callAPI({
            mode: 'warnings'
        }).then(function(response) {

            // Reset it all
            self.allWarnings.removeAll();
            if(response) {
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

    // Clear warnings through this special URL..
    self.clearWarnings = function() {
        // Activate
        callSpecialAPI("./status/clearwarnings/").done(self.refresh)
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
        if(!self.speedLimitInt()) return;

        // Update
        if(self.speedLimitInt() != newValue) {
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
        // Ignore updates before the page is done
        if(!self.hasStatusInfo()) return;

        // Something changes
        callAPI({
            mode: 'queue',
            name: 'change_complete_action',
            value: $(event.target).val()
        })

        // Top stop blinking while the API is calling
        self.onQueueFinish($(event.target).val())
    }

    // Use global settings or device-specific?
    self.useGlobalOptions.subscribe(function(newValue) {
        // Reload in case of enabling global options
        if(newValue) document.location = document.location;
    })

    // Update refreshrate
    self.refreshRate.subscribe(function(newValue) {
        // Refresh now
        self.refresh();

        // Save in config if global-settings
        if(self.useGlobalOptions()) {
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
        if(fileName) $('.btn-file em').text(fileName)
    }

    // From the upload
    self.addNZBFromFileForm = function(form) {
        // Anything?
        if(!$(form.nzbFile)[0].files[0]) {
            $('.btn-file').attr('style', 'border-color: red !important')
            setTimeout(function() { $('.btn-file').css('border-color', '') }, 2000)
            return false;
        }

        // Upload
        self.addNZBFromFile($(form.nzbFile)[0].files);

        // Hide modal, upload will reset the form
        $("#modal-add-nzb").modal("hide");
    }
    // From URL
    self.addNZBFromURL = function(form) {
        // Anything?
        if(!$(form.nzbURL).val()) {
            $(form.nzbURL).attr('style', 'border-color: red !important')
            setTimeout(function() { $(form.nzbURL).css('border-color', '') }, 2000)
            return false;
        }

        // Build request
        var theCall = {
            mode: "addurl",
            name: $(form.nzbURL).val(),
            nzbname: $('#nzbname').val(),
            script: $('#modal-add-nzb select[name="Post-processing"]').val(),
            priority: $('#modal-add-nzb select[name="Priority"]').val(),
            pp: $('#modal-add-nzb select[name="Processing"]').val()
        }

        // Optional, otherwise they get mis-labeled if left empty
        if($('#modal-add-nzb select[name="Category"]').val() != '*') theCall.cat = $('#modal-add-nzb select[name="Category"]').val()
        if($('#modal-add-nzb select[name="Processing"]').val()) theCall.pp = $('#modal-add-nzb select[name="Category"]').val()

        // Add
        callAPI(theCall).then(function(r) {
            // Hide and reset/refresh
            self.refresh()
            $("#modal-add-nzb").modal("hide");
            form.reset()
            $('#nzbname').val('')
        });

    }
    // From the upload or filedrop
    self.addNZBFromFile = function(files, fileindex) {
        // First file
        if(fileindex === undefined) {
            fileindex = 0
        }
        var file = files[fileindex]
        fileindex++

        // Check if it's maybe a folder, we can't handle those
        if(!file.type && file.size % 4096 == 0) return;

        // Add notification
        showNotification('.main-notification-box-uploading', 0, fileindex)

        // Adding a file happens through this special function
        var data = new FormData();
        data.append("name", file);
        data.append("mode", "addfile");
        data.append("nzbname", $('#nzbname').val());
        data.append("script", $('#modal-add-nzb select[name="Post-processing"]').val())
        data.append("priority", $('#modal-add-nzb select[name="Priority"]').val())
        data.append("apikey", apiKey);

        // Optional, otherwise they get mis-labeled if left empty
        if($('#modal-add-nzb select[name="Category"]').val() != '*') data.append("cat", $('#modal-add-nzb select[name="Category"]').val());
        if($('#modal-add-nzb select[name="Processing"]').val()) data.append("pp", $('#modal-add-nzb select[name="Processing"]').val());

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
            if(fileindex < files.length) {
                // Do the next one
                self.addNZBFromFile(files, fileindex)
            } else {
                // Refresh
                self.refresh();
                // Hide notification
                hideNotification('.main-notification-box-uploading')
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

        // Make it spin
        self.hasStatusInfo(false)

        // Load the custom status info
        callAPI({ mode: 'fullstatus', skip_dashboard: (!statusFullRefresh)*1 }).then(function(data) {
            // Update basic
            self.statusInfo.loglevel(data.status.loglevel)
            self.statusInfo.folders(data.status.folders)

            // Update the full set
            if(statusFullRefresh) {
                self.statusInfo.pystone(data.status.pystone)
                self.statusInfo.cpumodel(data.status.cpumodel)
                self.statusInfo.downloaddir(data.status.downloaddir)
                self.statusInfo.downloaddirspeed(data.status.downloaddirspeed)
                self.statusInfo.completedir(data.status.completedir)
                self.statusInfo.completedirspeed(data.status.completedirspeed)
                self.statusInfo.internetbandwidth(data.status.internetbandwidth)
                self.statusInfo.dnslookup(data.status.dnslookup)
                self.statusInfo.localipv4(data.status.localipv4)
                self.statusInfo.publicipv4(data.status.publicipv4)
                self.statusInfo.ipv6(data.status.ipv6 || glitterTranslate.noneText)
                // Loaded disk info
                self.hasPerformanceInfo(true)
            }

            // Update the servers
            if(self.statusInfo.servers().length != data.status.servers.length) {
                // Only now we can subscribe to the log-level-changes! (only at start)
                if(self.statusInfo.servers().length == 0) {
                    self.statusInfo.loglevel.subscribe(function(newValue) {
                        // Update log-level
                        callSpecialAPI('./status/change_loglevel/', {
                            loglevel: newValue
                        });
                    })
                }

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
                        'serverconnections': ko.observableArray(this.serverconnections)
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
                    activeServer.serverconnections(this.serverconnections)
                })
            }

            // Add tooltips to possible new items
            if(!isMobile) $('#modal-options [data-tooltip="true"]').tooltip({ trigger: 'hover', container: 'body' })

            // Stop it spin
            self.hasStatusInfo(true)
        });
    }

    // Do a disk-speedtest
    self.testDiskSpeed = function(item, event) {
        self.hasPerformanceInfo(false)

        // Run it and then display it
        callSpecialAPI('./status/dashrefresh/').then(function() {
            self.loadStatusInfo(true, true)
        })
    }

    // Download a test-NZB
    self.testDownload = function(data, event) {
        var nzbSize = $(event.target).data('size')

        // Maybe it was a click on the icon?
        if(nzbSize == undefined) {
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
        callSpecialAPI("./status/unblock_server/", {
            server: servername
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
            if(!$('#options_connections').is(':visible') && connectionRefresh) {
                // Stop refreshing
                clearInterval(connectionRefresh)
                return
            }
            // Only when we show them
            if(self.showActiveConnections()) {
                self.loadStatusInfo()
            }
        }, self.refreshRate() * 1000)
    })

    // On close of the tab
    $('.nav-tabs a[href="#options_connections"]').on('hidden.bs.tab', function() {
        checkSize()
    })

    // Function that handles the actual sizing of connections tab
    function checkSize() {
        // Any connections?
        if(self.showActiveConnections() && $('#options_connections').is(':visible') && $('.table-server-connections').height() > 1) {
            var mainWidth = $('.main-content').width()
            $('#modal-options .modal-dialog').width(mainWidth*0.85 > 650 ? mainWidth*0.85 : '')
        } else {
            // Small again
            $('#modal-options .modal-dialog').width('')
        }
    }

    // Make sure Connections get refreshed also after open->close->open
    $('#modal-options').on('show.bs.modal', function () {
        // Trigger
        $('.nav-tabs a[href="#options_connections"]').trigger('shown.bs.tab')
    })

    // Orphaned folder processing
    self.folderProcess = function(folder, htmlElement) {
        // Hide tooltips (otherwise they stay forever..)
        $('#options-orphans [data-tooltip="true"]').tooltip('hide')

        // Show notification on delete
        if($(htmlElement.currentTarget).data('action') == 'delete') {
            showNotification('.main-notification-box-removing', 1000)
        } else {
            // Adding back to queue
            showNotification('.main-notification-box-sendback', 2000)
        }

        // Activate
        callSpecialAPI("./status/" + $(htmlElement.currentTarget).data('action'), {
            name: $("<div/>").html(folder).text()
        }).then(function() {
            // Remove item and load status data
            $(htmlElement.currentTarget).parent().parent().fadeOut(fadeOnDeleteDuration)
            // Refresh
            self.loadStatusInfo(true, true)
            // Hide notification
            hideNotification(true)
        })
    }

    // Orphaned folder deletion of all
    self.removeAllOrphaned = function() {
        if(!self.confirmDeleteHistory() || confirm(glitterTranslate.clearWarn)) {
             // Show notification
            showNotification('.main-notification-box-removing-multiple', 0, self.statusInfo.folders().length)
            // Delete them all
            callSpecialAPI("./status/delete_all/").then(function() {
                // Remove notifcation and update screen
                hideNotification(true)
                self.loadStatusInfo(true, true)
            })
        }
    }

    // Orphaned folder adding of all
    self.addAllOrphaned = function() {
        if(!self.confirmDeleteHistory() || confirm(glitterTranslate.clearWarn)) {
             // Show notification
            showNotification('.main-notification-box-sendback')
            // Delete them all
            callSpecialAPI("./status/add_all/").then(function() {
                // Remove notifcation and update screen
                hideNotification(true)
                self.loadStatusInfo(true, true)
            })
        }
    }

    // Toggle Glitter's compact layout dynamically
    self.displayCompact.subscribe(function() {
        $('body').toggleClass('container-compact')
    })

    // Toggle Glitter's tabbed modus
    self.displayTabbed.subscribe(function() {
        $('body').toggleClass('container-tabbed')
    })

    /**
         SABnzb options
    **/
    // Shutdown
    self.shutdownSAB = function() {
        if(confirm(glitterTranslate.shutdown)) {
            // Show notification and return true to follow the URL
            showNotification('.main-notification-box-shutdown')
            return true
        }
    }
    // Restart
    self.restartSAB = function() {
        if(!confirm(glitterTranslate.restart)) return;
        // Call restart function
        callSpecialAPI("./config/restart/")

        // Set counter, we need at least 15 seconds
        self.isRestarting(Math.max(1, Math.floor(15 / self.refreshRate())));
        // Force refresh in case of very long refresh-times
        if(self.refreshRate() > 30) {
            setTimeout(self.refresh, 30 * 1000)
        }
    }
    // Queue actions
    self.doQueueAction = function(data, event) {
        // Event
        var theAction = $(event.target).data('mode');
        // Show notification if available
        if(['rss_now', 'watched_now'].indexOf(theAction) > -1) {
            showNotification('.main-notification-box-' + theAction, 2000)
        }
        // Send to the API
        callAPI({ mode: theAction })
    }
    // Repair queue
    self.repairQueue = function() {
        if(!confirm(glitterTranslate.repair)) return;
        // Hide the modal and show the notifucation
        $("#modal-options").modal("hide");
        showNotification('.main-notification-box-queue-repair')
        // Call the API
        callSpecialAPI("./config/repair/").then(function() {
            hideNotification(true)
        })
    }
    // Force disconnect
    self.forceDisconnect = function() {
        // Show notification
        showNotification('.main-notification-box-disconnect', 3000)
        // Call API
        callSpecialAPI("./status/disconnect/").then(function() {
            $("#modal-options").modal("hide");
        })
    }

    /***
        Retrieve config information and do startup functions
    ***/
    // Force compact mode as fast as possible
    if(localStorageGetItem('displayCompact') === 'true') {
        // Add extra class
        $('body').addClass('container-compact')
    }

    // Tabbed layout?
    if(localStorageGetItem('displayTabbed') === 'true') {
        $('body').addClass('container-tabbed')
    }

    // Get the speed-limit, refresh rate and server names
    callAPI({
        mode: 'get_config'
    }).then(function(response) {
        // Do we use global, or local settings?
        if(self.useGlobalOptions()) {
            // Set refreshrate (defaults to 1/s)
            if(!response.config.misc.refresh_rate) response.config.misc.refresh_rate = 1;
            self.refreshRate(response.config.misc.refresh_rate.toString());

            // Set history limit
            self.history.paginationLimit(response.config.misc.history_limit.toString())

            // Set queue limit
            self.queue.paginationLimit(response.config.misc.queue_limit.toString())
        }

        // Set bandwidth limit
        if(!response.config.misc.bandwidth_max) response.config.misc.bandwidth_max = false;
        self.bandwithLimit(response.config.misc.bandwidth_max);

        // Save servers (for reporting functionality of OZnzb)
        self.servers = response.config.servers;

        // Update message
        if(newRelease) {
            self.allMessages.push({
                index: 'UpdateMsg',
                type: glitterTranslate.status['INFO'],
                text: ('<a class="queue-update-sab" href="'+newReleaseUrl+'" target="_blank">'+glitterTranslate.updateAvailable+' '+newRelease+' <span class="glyphicon glyphicon-save"></span></a>'),
                css: 'info'
            });
        }

        // Message about cache - Not for 5 days if user ignored it
        if(!response.config.misc.cache_limit && localStorageGetItem('CacheMsg')*1+(1000*3600*24*5) < Date.now()) {
            self.allMessages.push({
                index: 'CacheMsg',
                type: glitterTranslate.status['INFO'],
                text: ('<a href="./config/general/#cache_limit">'+glitterTranslate.useCache.replace(/<br \/>/g, " ")+' <span class="glyphicon glyphicon-cog"></span></a>'),
                css: 'info',
                clear: function() { self.clearMessages('CacheMsg')}
            });
        }

        // Message about tips and tricks, only once
        if(response.config.misc.notified_new_skin < 2) {
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
    var orphanMsg = localStorageGetItem('OrphanedMsg')*1+(1000*3600*24*5) < Date.now();
    // Delay the check
    if(orphanMsg) {
        setTimeout(self.loadStatusInfo, 200);
    }

    // On any status load we check Orphaned folders
    self.hasStatusInfo.subscribe(function(finishedLoading) {
        // Loaded or just starting?
        if(!finishedLoading) return;

        // Orphaned folders? If user clicked away we check again in 5 days
        if(self.statusInfo.folders().length >= 3 && orphanMsg) {
            // Check if not already there
            if(!ko.utils.arrayFirst(self.allMessages(), function(item) { return item.index == 'OrphanedMsg' })) {
                self.allMessages.push({
                    index: 'OrphanedMsg',
                    type: glitterTranslate.status['INFO'],
                    text: glitterTranslate.orphanedJobsMsg + ' <a href="#" onclick="showOrphans()"><span class="glyphicon glyphicon-wrench"></span></a>',
                    css: 'info',
                    clear: function() { self.clearMessages('OrphanedMsg')}
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
    if(!hasLocalStorage && localStorageGetItem('LocalStorageMsg')*1+(1000*3600*24*20) < Date.now()) {
        self.allMessages.push({
            index: 'LocalStorageMsg',
            type: glitterTranslate.status['WARNING'].replace(':', ''),
            text: glitterTranslate.noLocalStorage,
            css: 'warning',
            clear: function() { self.clearMessages('LocalStorageMsg')}
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
    }, 60*1000)

    /***
        End of main functions, start of the fun!
    ***/
    // Trigger first refresh
    self.interval = setTimeout(self.refresh, parseInt(self.refreshRate()) * 1000);

    // And refresh now!
    self.refresh()

    // Activate tooltips
    if(!isMobile) $('[data-tooltip="true"]').tooltip({ trigger: 'hover', container: 'body' })
}
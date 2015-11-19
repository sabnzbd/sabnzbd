/******
        
        Glitter V1
        By Safihre (2015) - safihre@sabnzbd.org
        
        Code extended from Shiny-template
        Code examples used from Knockstrap-template

********/

/**
    FIX for IE8 and below not having IndexOf for array's
**/
if(!Array.prototype.indexOf) {
    Array.prototype.indexOf = function(elt /*, from*/ ) {
        var len = this.length >>> 0;
        var from = Number(arguments[1]) || 0;
        from = (from < 0) ? Math.ceil(from) : Math.floor(from);
        if(from < 0) from += len;
        for(; from < len; from++) {
            if(from in this && this[from] === elt) return from;
        }
        return -1;
    };
}

/**
    Base variables and functions
**/
var fadeOnDeleteDuration = 400; // ms after deleting a row
var isMobile = (/android|webos|iphone|ipad|ipod|blackberry|iemobile|opera mini/i.test(navigator.userAgent.toLowerCase()));

// For mobile we disable zoom while a modal is being opened 
// so it will not zoom unnecessarily on the modal
if(isMobile) {
    $('.modal').on('show.bs.modal', function (e) {
        $('meta[name="viewport"]').attr('content', 'width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no');
    })
    // Restore on modal-close. Need timeout, otherwise it doesn't work
    $('.modal').on('hidden.bs.modal', function (e) {
        setTimeout(function() {
            $('meta[name="viewport"]').attr('content', 'width=device-width, initial-scale=1');
        },500)
    })
}

/**
    GLITTER CODE
**/
$(function() {

    // Basic API-call
    function callAPI(data) {
        // Fill basis var's
        data.output = "json";
        data.apikey = apiKey;
        var ajaxQuery = $.ajax({
            url: "tapi",
            type: "GET",
            cache: false,
            data: data,
            timeout: 6000 // Wait a little longer on mobile connections
        });

        return $.when(ajaxQuery);
    }

    // Special API call
    function callSpecialAPI(url, data) {
        // Did we get input?
        if(data == undefined) data = {};
        // Fill basis var's
        data.output = "json";
        data.apikey = apiKey;
        var ajaxQuery = $.ajax({
            url: url,
            type: "GET",
            cache: false,
            data: data
        });

        return $.when(ajaxQuery);
    }

    /**
        Handle visibility changes so we 
        do only incremental update when not visible
    **/
    var pageIsVisible = true;
    // Set the name of the hidden property and the change event for visibility
    var hidden, visibilityChange;
    if(typeof document.hidden !== "undefined") { // Opera 12.10 and Firefox 18 and later support 
        hidden = "hidden";
        visibilityChange = "visibilitychange";
    } else if(typeof document.mozHidden !== "undefined") {
        hidden = "mozHidden";
        visibilityChange = "mozvisibilitychange";
    } else if(typeof document.msHidden !== "undefined") {
        hidden = "msHidden";
        visibilityChange = "msvisibilitychange";
    } else if(typeof document.webkitHidden !== "undefined") {
        hidden = "webkitHidden";
        visibilityChange = "webkitvisibilitychange";
    }

    // Set the global visibility  
    function handleVisibilityChange() {
        if(document[hidden]) {
            pageIsVisible = false;
        } else {
            pageIsVisible = true;
        }
    }

    // Add event listener only for supported browsers
    if(typeof document.addEventListener !== "undefined" && typeof document[hidden] !== "undefined") {
        // Handle page visibility change   
        document.addEventListener(visibilityChange, handleVisibilityChange, false);
    }

    /**
        Define main view model
    **/
    function ViewModel() {
        // Initialize models
        var self = this;
        self.queue = new QueueListModel(this);
        self.history = new HistoryListModel(this);
        self.filelist = new Fileslisting(this);

        // Set information varibales
        self.title = ko.observable()
        self.isRestarting = ko.observable(false);
        self.useGlobalOptions = ko.observable(true).extend({ persist: 'useGlobalOptions' });
        self.refreshRate = ko.observable(1).extend({ persist: 'pageRefreshRate' });
        self.dateFormat = ko.observable('DD/MM/YYYY HH:mm').extend({ persist: 'pageDateFormat' });
        self.confirmDeleteQueue = ko.observable(true).extend({ persist: 'confirmDeleteQueue' });
        self.confirmDeleteHistory = ko.observable(true).extend({ persist: 'confirmDeleteHistory' });
        self.extraColumn = ko.observable('').extend({ persist: 'extraColumn' });
        self.hasStatusInfo = ko.observable(false); // True when we load it
        self.showActiveConnections = ko.observable(false);
        self.speed = ko.observable(0);
        self.speedMetric = ko.observable();
        self.speedMetrics = { K: "KB/s", M: "MB/s", G: "GB/s" };
        self.bandwithLimit = ko.observable(false);
        self.speedLimit = ko.observable(100).extend({ rateLimit: { timeout: 200, method: "notifyWhenChangesStop" } });
        self.speedLimitInt = ko.observable(false); // We need the 'internal' counter so we don't trigger the API all the time
        self.downloadsPaused = ko.observable(false);
        self.timeLeft = ko.observable("0:00");
        self.diskSpaceLeft1 = ko.observable();
        self.diskSpaceLeft2 = ko.observable();
        self.queueDataLeft = ko.observable();
        self.queueDataLeftMB = ko.observable(); // To check if we have enough diskspace left
        self.quotaLimit = ko.observable();
        self.quotaLimitLeft = ko.observable();
        self.nrWarnings = ko.observable(0);
        self.allWarnings = ko.observableArray([]);
        self.allMessages = ko.observableArray([]);
        self.onQueueFinish = ko.observable('');
        self.speedHistory = [];
        self.statusInfo = {};
        
        /***
            Dynamic functions
        ***/

        // Make the speedlimit tekst
        self.speedLimitText = ko.computed(function() {
            // Set?
            if(!self.bandwithLimit()) return;
            
            // The text 
            bandwithLimitText = self.bandwithLimit().replace(/[^a-zA-Z]+/g, '');
            
            // Only the number
            bandwithLimitNumber = parseInt(self.bandwithLimit());
            speedLimitNumber = (bandwithLimitNumber * (self.speedLimit() / 100));
            
            // Trick to only get decimal-point when needed
            speedLimitNumber = Math.round(speedLimitNumber*10)/10;
            
            // Fix it for lower than 1MB/s
            if(bandwithLimitText == 'M' && speedLimitNumber < 1) {
                bandwithLimitText = 'K';
                speedLimitNumber = Math.round(speedLimitNumber * 1024);
            }

            // Show text
            return self.speedLimit() + '% (' + speedLimitNumber + ' ' + self.speedMetrics[bandwithLimitText] + ')';
        });

        // Dynamic speed text function
        self.speedText = ko.computed(function() {
            return self.speed() + ' ' + (self.speedMetrics[self.speedMetric()] ? self.speedMetrics[self.speedMetric()] : "KB/s");
        });

        // Dynamic icon
        self.SABIcon = ko.computed(function() {
            if(self.downloadsPaused()) {
                return './staticcfg/ico/faviconpaused.ico';
            } else {
                return './staticcfg/ico/favicon.ico';
            }
        })

        // Dynamic queue length check
        self.hasQueue = ko.computed(function() {
            return(self.queue.queueItems().length > 0 || self.queue.searchTerm())
        })

        // Dynamic history length check
        self.hasHistory = ko.computed(function() {
            // We also 'have history' if we can't find any results of the search or there are no failed ones
            return (self.history.historyItems().length > 0 || self.history.searchTerm() || self.history.showFailed())
        }).extend({ rateLimit: { method: "notifyWhenChangesStop", timeout: 100 }});
        
        self.hasWarnings = ko.computed(function() {
            return(self.allWarnings().length > 0)
        })
        
        // Check for any warnings/messages
        self.hasMessages = ko.computed(function() {
            return self.nrWarnings() > 0 || self.allMessages().length > 0;
        })

        // Update main queue
        self.updateQueue = function(response) {
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
                Basic information
            ***/
            // Queue left
            self.queueDataLeft(response.queue.mbleft > 0 ? response.queue.sizeleft : '')
            self.queueDataLeftMB(response.queue.mbleft > 0 ? response.queue.mbleft : 0)

            // Paused?
            self.downloadsPaused(response.queue.paused);

            // Finish action. Replace null with empty
            self.onQueueFinish(response.queue.finishaction ? response.queue.finishaction : '');

            // Disk sizes
            self.diskSpaceLeft1(parseFloat(response.queue.diskspace1).toFixed(1))

            // Same sizes? Then it's all 1 disk!
            if(response.queue.diskspace1 != response.queue.diskspace2) {
                self.diskSpaceLeft2(parseFloat(response.queue.diskspace2).toFixed(1))
            }

            // Quota
            self.quotaLimit(response.queue.quota)
            self.quotaLimitLeft(response.queue.left_quota)

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
            speedSplit = response.queue.speed.split(/\s/);
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
            self.speedLimitInt(response.queue.speedlimit)

            // Only update from external source when user isn't doing input
            if(!$('.speedlimit-dropdown .btn-group .btn-group').is('.open')) {
                self.speedLimit(response.queue.speedlimit)
            }

            /***
                Download timing and pausing
            ***/
            timeString = response.queue.timeleft;
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
                    pauseSplit = response.queue.pause_int.split(/:/);
                    seconds = parseInt(pauseSplit[0]) * 60 + parseInt(pauseSplit[1]);
                    hours = Math.floor(seconds / 3600);
                    minutes = Math.floor((seconds -= hours * 3600) / 60);
                    seconds -= minutes * 60;
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

        // Refresh function
        self.refresh = function() {
            /**
                Limited refresh
            **/
            // Only update the title when page not visible
            if(!pageIsVisible) {
                // Request new title 
                callSpecialAPI('queue/', {}).then(function(data) {
                        // Split title & speed
                        dataSplit = data.split('|||');

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
                    })
                // Do not continue!
                return;
            }

            /**
                Full refresh
            **/
            // Do requests for full information
            // Catch the fail to display message
            queueApi = callAPI({
                mode: "queue",
                search: self.queue.searchTerm(),
                start: self.queue.pagination.currentStart(),
                limit: parseInt(self.queue.paginationLimit())
            }).then(
                self.updateQueue,
                function() {
                    self.isRestarting(1)
                }
            );
            callAPI({
                mode: "history",
                search: self.history.searchTerm(),
                failed_only: self.history.showFailed()*1,
                start: self.history.pagination.currentStart(),
                limit: parseInt(self.history.paginationLimit())
            }).then(self.updateHistory);

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
        self.pauseTime = function(e, b) {
            pauseDuration = $(b.currentTarget).data('time');
            callAPI({
                mode: 'config',
                name: 'set_pause',
                value: pauseDuration
            });
            self.downloadsPaused(true);
        };
        
        // Custom pause-timer
        self.customPauseTime = function() {
            // Was it loaded already?
            if(!Date.i18n) {
                 jQuery.getScript('./static/javascripts/date.min.js').then(function() {
                    // After loading we start again
                    self.customPauseTime()
                 })
                 return;
            }
            
            // Pop the question
            var pausePrompt = prompt(glitterTranslate.pausePrompt);
            var pauseParsed = Date.parse(pausePrompt);
            
            // Did we get it?
            if(pauseParsed) {
                // Is it just now?
                if(pauseParsed <= Date.parse('now')) {
                    // Try again with the '+' in front, the parser doesn't get 100min
                    pauseParsed = Date.parse('+' + pausePrompt);
                }
                
                // Calculate difference in minutes
                var pauseDuration = Math.round((pauseParsed - Date.parse('now'))/1000/60);
                
                // If in the future
                if(pauseDuration > 0) {
                    callAPI({
                        mode: 'config',
                        name: 'set_pause',
                        value: pauseDuration
                    });
                    self.downloadsPaused(true);
                }
            } else if(pausePrompt) {
                // No.. And user did not press cancel
                alert(glitterTranslate.pausePromptFail)
                self.customPauseTime();
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
                        // Split warning into parts
                        var warningSplit = warning.split(/\n/);
                        
                        // Reformat CSS label and date
                        var warningData = {
                            index: index,
                            type: glitterTranslate.status[warningSplit[1]].slice(0, -1),
                            text: warningSplit.slice(2).join('<br/>').replace(/ /g, '\u00A0'), // Recombine if multiple lines
                            date: displayDateTime(warningSplit[0], self.dateFormat(), 'YYYY-MM-DD HH:mm'),
                            timestamp: moment(warningSplit[0], 'YYYY-MM-DD HH:mm').unix(),
                            css: (warningSplit[1] == "ERROR" ? "danger" : warningSplit[1] == "WARNING" ? "warning" : "info"),
                            clear: self.clearWarnings
                        };

                        self.allWarnings.push(warningData)
                    })
                }
            });
        })

        // Clear warnings through this weird URL..
        self.clearWarnings = function() {
            if(!self.confirmDeleteQueue() || confirm(glitterTranslate.clearWarn))
                // Activate
                callSpecialAPI("status/clearwarnings")
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
        self.onQueueFinish.subscribe(function(newValue) {
            // Something changes
            callAPI({
                mode: 'queue',
                name: 'change_complete_action',
                value: newValue
            })
        })
        
        // Use global settings or device-specific?
        self.useGlobalOptions.subscribe(function(newValue) {
            // Reload in case of enabling global options
            if(newValue) document.location = document.location;
        })

        // Update refreshrate
        self.refreshRate.subscribe(function(newValue) {
            // Set in javascript
            clearInterval(self.interval)
            self.interval = setInterval(self.refresh, parseInt(newValue) * 1000);
            
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

        // NOTE: Adjusted from Knockstrap template
        self.addNZBFromFileForm = function(form) {
            self.addNZBFromFile($(form.nzbFile)[0].files[0]);

            // After that, hide and reset
            $("#modal_add_nzb").modal("hide");
            form.reset()
            $('#nzbname').val('')
            $('.btn-file em').html(glitterTranslate.chooseFile + '&hellip;')
        }
        self.addNZBFromURL = function(form) {
            // Add 
            callAPI({
                mode: "addurl",
                name: $(form.nzbURL).val(),
                nzbname: $('#nzbname').val(),
                cat: $('#modal_add_nzb select[name="Category"]').val() == '' ? 'Default' : $('#modal_add_nzb select[name="Category"]').val(),
                script: $('#modal_add_nzb select[name="Post-processing"]').val() == '' ? 'Default' : $('#modal_add_nzb select[name="Post-processing"]').val(),
                priority: $('#modal_add_nzb select[name="Priority"]').val() == '' ? -100 : $('#modal_add_nzb select[name="Priority"]').val(),
                pp: $('#modal_add_nzb select[name="Processing"]').val() == '' ? -1 : $('#modal_add_nzb select[name="Processing"]').val()
            }).then(function(r) {
                // Hide and reset/refresh
                self.refresh()
                $("#modal_add_nzb").modal("hide");
                form.reset()
                $('#nzbname').val('')
            });

        }
        self.addNZBFromFile = function(file) {
            // Adding a file happens through this special function
            var data = new FormData();
            data.append("name", file);
            data.append("mode", "addfile");
            data.append("nzbname", $('#nzbname').val());
            data.append("cat", $('#modal_add_nzb select[name="Category"]').val() == '' ? 'Default' : $('#modal_add_nzb select[name="Category"]').val()); // Default category
            data.append("script", $('#modal_add_nzb select[name="Post-processing"]').val() == '' ? 'Default' : $('#modal_add_nzb select[name="Post-processing"]').val()); // Default script
            data.append("priority", $('#modal_add_nzb select[name="Priority"]').val() == '' ? -100 : $('#modal_add_nzb select[name="Priority"]').val()); // Default priority
            data.append("pp", $('#modal_add_nzb select[name="Processing"]').val() == '' ? -1 : $('#modal_add_nzb select[name="Processing"]').val()); // Default post-processing options
            data.append("apikey", apiKey);
            // Add 
            $.ajax({
                url: "tapi",
                type: "POST",
                cache: false,
                processData: false,
                contentType: false,
                data: data
            }).then(function(r) {
                // Refresh
                self.refresh();
            });

        }

        // Load status info
        self.loadStatusInfo = function(b, event) {
            // Reset
            self.hasStatusInfo(false)
            
            // Full refresh? Only on click and for the status-screen
            var statusFullRefresh = (event != undefined) && $('#options_status').hasClass('active');
            var strStatusUrl = statusFullRefresh ? 'status/' : 'status/?skip_dashboard=1';

            // Load the custom status info
            callSpecialAPI(strStatusUrl).then(function(data) {
                // Parse JSON
                parsedJSON = ko.utils.parseJson(data);
                
                // Making the new objects
                self.statusInfo.status = ko.mapping.fromJS(parsedJSON.status);
                
                // Only when we do full refresh we have dashboard-info
                if(statusFullRefresh) self.statusInfo.dashboard = ko.mapping.fromJS(parsedJSON.dashboard);

                // Only now we can subscribe to the log-level-changes!
                self.statusInfo.status.loglevel.subscribe(function(newValue) {
                    // Update log-level
                    callSpecialAPI('status/change_loglevel', {
                        loglevel: newValue
                    });
                })
                
                // Show again
                self.hasStatusInfo(true)

                // Add tooltips again
                if(!isMobile) $('#modal_options [data-toggle="tooltip"]').tooltip({ trigger: 'hover', container: 'body' })
            });
        }

        // Do a disk-speedtest
        self.testDiskSpeed = function() {
            // Hide tooltips (otherwise they stay forever..)
            $('#options_status [data-toggle="tooltip"]').tooltip('hide')
            // Hide before running the test
            self.hasStatusInfo(false)
            // Run it and then display it
            callSpecialAPI('status/dashrefresh').then(function() {
                self.loadStatusInfo(true, true)
            })
        }

        // Unblock server
        self.unblockServer = function(servername) {
            callSpecialAPI("status/unblock_server", {
                server: servername
            }).then(function() {
                $("#modal_options").modal("hide");
            })
        }

        // Orphaned folder processing
        self.folderProcess = function(folder, htmlElement) {
            // Hide tooltips (otherwise they stay forever..)
            $('#options_orphans [data-toggle="tooltip"]').tooltip('hide')
            
            // Activate
            callSpecialAPI("status/" + $(htmlElement.currentTarget).data('action'), {
                name: folder.folder()
            }).then(function() {
                // Remove item and load status data
                $(htmlElement.currentTarget).parent().parent().fadeOut(fadeOnDeleteDuration)
                // Refresh
                self.loadStatusInfo()
            })
        }

        // Orphaned folder deletion of all
        self.removeAllOrphaned = function() {
            if(!self.confirmDeleteHistory() || confirm(glitterTranslate.clearWarn)) {
                // Delete them all
                callSpecialAPI("status/delete_all").then(self.loadStatusInfo)
            }     
        }

        /**
             SABnzb options
        **/
        // Shutdown
        self.shutdownSAB = function() {
            return confirm(glitterTranslate.shutdown);
        }
        // Restart
        self.restartSAB = function() {
            if(!confirm(glitterTranslate.restart)) return;
            // Call restart function
            callSpecialAPI("config/restart")

            // Set counter, we need at least 15 seconds
            self.isRestarting(Math.max(1, Math.floor(15 / self.refreshRate())));
            // Force refresh in case of very long refresh-times
            if(self.refreshRate() > 30) {
                setTimeout(self.refresh, 30 * 1000)
            }
        }
        // Queue actions
        self.doQueueAction = function(data, event) {
            // Send to the API
            callAPI({ mode: $(event.target).data('mode') })
        }
        // Repair queue
        self.repairQueue = function() {
            if(!confirm(glitterTranslate.repair)) return;
            callSpecialAPI("config/repair").then(function() {
                $("#modal_options").modal("hide");
            })
        }
        // Force disconnect
        self.forceDisconnect = function() {
            callSpecialAPI("status/disconnect").then(function() {
                $("#modal_options").modal("hide");
            })
        }
        
        /***
            Retrieve config information and do startup functions
        ***/
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
        })
        
        // Orphaned folder check - Not for 5 days if user ignored it
        var orphanMsg = localStorageGetItem('OrphanedMsg')*1+(1000*3600*24*5) < Date.now();
        // Delay the check
        if(orphanMsg) {
            setTimeout(self.loadStatusInfo, 2000);
        }
        
        // On any status load we check Orphaned folders 
        self.hasStatusInfo.subscribe(function(finishedLoading) { 
            // Loaded or just starting?
            if(!finishedLoading) return;
            
            // Orphaned folders? If user clicked away we check again in 5 days
            if(self.statusInfo.status.folders().length >= 3 && orphanMsg) {
                // Check if not already there
                if(!ko.utils.arrayFirst(self.allMessages(), function(item) { return item.index == 'OrphanedMsg' })) {
                    self.allMessages.push({
                        index: 'OrphanedMsg',
                        type: 'INFO',
                        text: glitterTranslate.orphanedJobsMsg + ' <a href="#" onclick="$(\'a[href=#modal_options]\').click().parent().click(); $(\'a[href=#options_orphans]\').click()"><span class="glyphicon glyphicon-wrench"></span></a>',
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
        
        // Update message
        if(newRelease) {
            self.allMessages.push({
                index: 'UpdateMsg',
                type: 'INFO',
                text: ('<a class="queue-update-sab" href="'+newReleaseUrl+'" target="_blank">'+glitterTranslate.updateAvailable+' '+newRelease+' <span class="glyphicon glyphicon-save"></span></a>'),
                css: 'info'
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
        // Set interval for refreshing queue
        self.interval = setInterval(self.refresh, parseInt(self.refreshRate()) * 1000);
        
        // And refresh now!
        self.refresh()

        // Activate tooltips
        if(!isMobile) $('[data-toggle="tooltip"]').tooltip({ trigger: 'hover', container: 'body' })
    }

    /**
        Model for the whole Queue with all it's items
    **/
    function QueueListModel(parent) {
        // Internal var's
        var self = this;
        self.parent = parent;
        self.dragging = false;

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
        self.dragStart = function(e) {
            self.dragging = true;
        }
        self.dragStop = function(e) {
            self.dragging = false;
            $(e.target).parent().removeClass('table-active-sorting')
        }

        // Update slots from API data
        self.updateFromData = function(data) {
            // Get all ID's'
            var itemIds = $.map(self.queueItems(), function(i) {
                return i.id;
            });
            
            // Reformat categories
            self.categoriesList($.map(data.categories, function(cat) {
                // Default?
                if(cat == '*') return { catValue: '*', catText: glitterTranslate.defaultText };
                return { catValue: cat, catText: cat };
            }))

            // Set categories and scripts and limit
            self.scriptsList(data.scripts)
            self.totalItems(data.noofslots);

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
                    self.queueItems.push(new QueueModel(self, item));

                    // Only now sort
                    self.queueItems.sort(function(a, b) {
                        return a.index() < b.index() ? -1 : 1;
                    });
                }
            });

            // Remove items that don't exist anymore
            $.each(itemIds, function() {
                var id = this.toString();
                self.queueItems.remove(ko.utils.arrayFirst(self.queueItems(), function(i) {
                    return i.id == id;
                }));
            });
        };

        // Move in sortable
        self.move = function(e) {
            var itemMoved = e.item;
            var itemReplaced = ko.utils.arrayFirst(self.queueItems(), function(i) {
                return i.index() == e.targetIndex;
            });

            itemMoved.index(e.targetIndex);
            itemReplaced.index(e.sourceIndex);

            callAPI({
                mode: "switch",
                value: itemMoved.id,
                value2: e.targetIndex
            }).then(function(r) {
                if(r.position != e.targetIndex) {
                    itemMoved.index(e.sourceIndex);
                    itemReplaced.index(e.targetIndex);
                }
            });
        };

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
            
            self.parent.refresh();
        });
        
        // Do we show search box. So it doesn't dissapear when nothing is found
        self.hasQueueSearch = ko.computed(function() {
            return (self.pagination.hasPagination() || self.searchTerm())
        })
        
        // Searching in queue (rate-limited in decleration)
        self.searchTerm.subscribe(function() {
            // If the refresh-rate is high we do a forced refresh
            if(parseInt(self.parent.refreshRate()) >2 ) {
                self.parent.refresh();
            }
            // Go back to page 1
            if(self.pagination.currentPage() != 1) {
                self.pagination.moveToPage(1);
            }
        })
        
        // Clear searchterm
        self.clearSearchTerm = function(objModel, event) {
            // Was it escape key or click?
            if(event.type == 'mousedown' || (event.keyCode && event.keyCode == 27)) {
                self.searchTerm('');
                self.parent.refresh();
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
            // Send call
            callAPI({
                mode: 'queue',
                name: 'sort',
                sort: sort,
                dir: dir
            }).then(function() {
                // Force a refresh and then re-sort
                parent.refresh().then(function() {
                    self.queueItems.sort(function(a, b) {
                        return a.index() < b.index() ? -1 : 1;
                    });
                })
            })
        }

        self.showMultiEdit = function() {
            // Update value
            self.isMultiEditing(!self.isMultiEditing())
            // Form
            $form = $('form.multioperations-selector')
            
            // Reset form
            $form[0].reset();
            
            // Is the multi-edit in view?
            if(($form.offset().top + $form.outerHeight(true)) > ($(window).scrollTop()+$(window).height())) {
                // Scroll to form
                $('html, body').animate({
                    scrollTop: $form.offset().top + $form.outerHeight(true) - $(window).height() + 'px'
                }, 'fast')
            }
            

            // Do update on close, to make sure it's all updated
            if(!self.isMultiEditing()) {
                self.parent.refresh();
            }
        }

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
                // Now we definitely have not checked them all
                $('#multiedit-checkall').prop('checked', false)
            }

            return true;
        }

        // Do the actual multi-update immediatly
        self.doMultiEditUpdate = function() {
            // Anything selected?
            if(self.multiEditItems().length < 1) return;
            
            // Retrieve the current settings
            newCat = $('.multioperations-selector select[name="Category"]').val()
            newScript = $('.multioperations-selector select[name="Post-processing"]').val()
            newPrior = $('.multioperations-selector select[name="Priority"]').val()
            newProc = $('.multioperations-selector select[name="Processing"]').val()
            newStatus = $('.multioperations-selector input[name="multiedit-status"]:checked').val()

            // List all the ID's
            strIDs = '';
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
            setTimeout(parent.refresh, 100)

        }

        // Selete all selected
        self.doMultiDelete = function() {
            if(!self.parent.confirmDeleteQueue() || confirm(glitterTranslate.removeDown)) {
                // List all the ID's
                strIDs = '';
                $.each(self.multiEditItems(), function(index) {
                    strIDs = strIDs + this.id + ',';
                })
    
                // Remove
                callAPI({
                    mode: 'queue',
                    name: 'delete',
                    del_files: 1,
                    value: strIDs
                }).then(function(response) {
                    if(response.status) {
                        $('.delete input:checked').parents('tr').fadeOut(fadeOnDeleteDuration, function() {
                            self.parent.refresh();
                        })
                        // Empty it
                        self.multiEditItems.removeAll();
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
                // Now let's see if all are checked, based on compare with total
                if($('.queue input[name="multiedit"]:checked').length == $('.queue input[name="multiedit"]').length) {
                    $('#multiedit-checkall').prop('checked', true)
                } else {
                    $('#multiedit-checkall').prop('checked', false)
                }
            }, 100)
        }, null, "arrayChange")
    }

    /**
        Model for each Queue item
    **/
    function QueueModel(parent, data) {
        var self = this;
        self.parent = parent;

        // Define all knockout variables
        self.id;
        self.index = ko.observable();
        self.name = ko.observable();
        self.status = ko.observable();
        self.isGrabbing = ko.observable(false);
        self.totalMB = ko.observable(0);
        self.remainingMB = ko.observable(0);
        self.avg_age = ko.observable(0);
        self.timeLeft = ko.observable();
        self.progressColor = ko.observable();
        self.missingText = ko.observable();
        self.category = ko.observable();
        self.script = ko.observable();
        self.priority = ko.observable();
        self.unpackopts = ko.observable();
        self.editingName = ko.observable(false);
        self.nameForEdit = ko.observable();
        self.pausedStatus = ko.observable();
        self.rating_avg_video = ko.observable(false);
        self.rating_avg_audio = ko.observable(false);

        // Functional vars        
        self.downloadedMB = ko.computed(function() {
            return(self.totalMB() - self.remainingMB()).toFixed(0);
        }, this);

        self.percentage = ko.computed(function() {
            return((self.downloadedMB() / self.totalMB()) * 100).toFixed(2);
        }, this);

        self.percentageRounded = ko.computed(function() {
            return fixPercentages(self.percentage())
        }, this);

        self.progressText = ko.computed(function() {
            return self.downloadedMB() + " MB / " + (self.totalMB() * 1).toFixed(0) + " MB";
        }, this);
        
        self.extraText = ko.computed(function() {
            // Picked anything?
            switch(self.parent.parent.extraColumn()) {
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
        })

        // Every update
        self.updateFromData = function(data) {
            // Things that need to be set
            self.id = data.nzo_id;
            self.name($.trim(data.filename));
            self.index(data.index);

            // General status
            if(data.status == 'Grabbing') {
                self.isGrabbing(true)
                return; // Important! Otherwise cat/script/priority get magically changed!
            } else if(self.isGrabbing()) {
                // Reset after the grabbing is done!
                self.isGrabbing(false)
            }

            // Set stats
            self.progressColor(''); // Reset
            self.status(data.status)
            self.totalMB(parseFloat(data.mb));
            self.remainingMB(parseFloat(data.mbleft));
            self.avg_age(data.avg_age)
            self.category(data.cat);
            self.priority(parent.priorityName[data.priority]);
            self.script(data.script);

            self.unpackopts(parseInt(data.unpackopts)) // UnpackOpts fails if not parseInt'd!
            self.pausedStatus(data.status == 'Paused');

            // If exists, otherwise false
            if(data.rating_avg_video !== undefined) {
                self.rating_avg_video(data.rating_avg_video === 0 ? '-' : data.rating_avg_video);
                self.rating_avg_audio(data.rating_avg_audio === 0 ? '-' : data.rating_avg_audio);
            }

            // Checking
            if(data.status == 'Checking') {
                self.progressColor('#58A9FA')
                self.timeLeft(glitterTranslate.checking);
            }

            // Check for missing data, the value is arbitrary!
            if(data.missing > 50) {
                self.progressColor('#F8A34E');
                self.missingText(data.missing + ' ' + glitterTranslate.misingArt)
            }

            // Set color   
            if((self.parent.parent.downloadsPaused() && data.priority != 'Force') || self.pausedStatus()) {
                self.timeLeft(glitterTranslate.paused);
                self.progressColor('#B7B7B7');
            } else if(data.status != 'Checking') {
                self.timeLeft(rewriteTime(data.timeleft));
            }
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
        self.editName = function() {
            // Change status and fill
            self.editingName(true)
            self.nameForEdit(self.name())
        }

        // Catch the submit action
        self.editingNameSubmit = function() {
            self.editingName(false)
        }

        // Do on change
        self.nameForEdit.subscribe(function(newName) {
            // Change?
            if(newName != self.name() && newName != "") {
                callAPI({
                        mode: 'queue',
                        name: "rename",
                        value: self.id,
                        value2: newName
                    })
                    .then(function(response) {
                        // Succes?
                        if(response.status) {
                            self.name(newName)
                            self.parent.parent.refresh;
                        }
                    })
            }
        })

        // See items
        self.showFiles = function() {
            // Trigger update
            parent.parent.filelist.loadFiles(self)
        }

        // Change of settings
        self.changeCat = function(itemObj) {
            callAPI({
                mode: 'change_cat',
                value: itemObj.id,
                value2: itemObj.category()
            })
        }
        self.changeScript = function(itemObj) {
            // Not on empty handlers
            if(!itemObj.script()) return;
            callAPI({
                mode: 'change_script',
                value: itemObj.id,
                value2: itemObj.script()
            })
        }
        self.changeProcessing = function(itemObj) {
            callAPI({
                mode: 'change_opts',
                value: itemObj.id,
                value2: itemObj.unpackopts()
            })
        }
        self.changePriority = function(itemObj) {
            // Not if we are fetching extra blocks for repair!
            if(itemObj.status() == 'Fetching') return
            callAPI({
                mode: 'queue',
                name: 'priority',
                value: itemObj.id,
                value2: itemObj.priority()
            })
        }

        // Remove 1 download from queue
        self.removeDownload = function(data, event) {
            if(!self.parent.parent.confirmDeleteQueue() || confirm(glitterTranslate.removeDow1)) {
                var itemToDelete = this;
                callAPI({
                    mode: 'queue',
                    name: 'delete',
                    del_files: 1,
                    value: this.id
                }).then(function(response) {
                    if(response.status) {
                        // Fade and remove
                        $(event.currentTarget).parent().parent().fadeOut(fadeOnDeleteDuration, function() {
                            parent.queueItems.remove(itemToDelete);
                            self.parent.parent.refresh();
                        })
                    }
                });
            }
        };

        // Update
        self.updateFromData(data);
    }

    /**
        Model for the whole History with all it's items
    **/
    function HistoryListModel(parent) {
        var self = this;
        self.parent = parent;

        // Variables
        self.historyItems = ko.observableArray([]);
        self.showFailed = ko.observable(false);
        self.searchTerm = ko.observable('').extend({ rateLimit: { timeout: 200, method: "notifyWhenChangesStop" } });
        self.paginationLimit = ko.observable(10).extend({ persist: 'historyPaginationLimit' });
        self.totalItems = ko.observable(0);
        self.pagination = new paginationModel(self);

        // Download history info
        self.downloadedToday = ko.observable();
        self.downloadedWeek = ko.observable();
        self.downloadedMonth = ko.observable();
        self.downloadedTotal = ko.observable();

        // Update function for history list
        self.updateFromData = function(data) {
            /***
                History list functions per item
            ***/
            var itemIds = $.map(self.historyItems(), function(i) {
                return i.historyStatus.nzo_id();
            });

            $.each(data.slots, function(index, slot) {
                var existingItem = ko.utils.arrayFirst(self.historyItems(), function(i) {
                    return i.historyStatus.nzo_id() == slot.nzo_id;
                });
                // Update or add?
                if(existingItem) {
                    existingItem.updateFromData(slot);
                    itemIds.splice(itemIds.indexOf(slot.nzo_id), 1);
                } else {
                    // Add history item
                    self.historyItems.push(new HistoryModel(self, slot));

                    // Only now sort so newest on top. completed is updated every time while download is waiting
                    // so doing the sorting every time would cause it to bounce around
                    self.historyItems.sort(function(a, b) {
                        return a.historyStatus.completed() > b.historyStatus.completed() ? -1 : 1;
                    });
                }
            });

            // Remove the un-used ones
            $.each(itemIds, function() {
                var id = this.toString();
                self.historyItems.remove(ko.utils.arrayFirst(self.historyItems(), function(i) {
                    return i.historyStatus.nzo_id() == id;
                }));
            });

            /***
                History information
            ***/
            self.totalItems(data.noofslots);
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
            self.parent.refresh();
        });

        // Retry a job
        self.retryJob = function(form) {
            // Adding a extra retry file happens through this special function
            var data = new FormData();
            data.append("nzbfile", $(form.nzbFile)[0].files[0]);
            data.append("job", $('#modal_retry_job input[name="retry_job_id"]').val());
            data.append("password", $('#retry_job_password').val());
            data.append("session", apiKey);

            // Add 
            $.ajax({
                url: "history/retry_pp",
                type: "POST",
                cache: false,
                processData: false,
                contentType: false,
                data: data
            }).then(function(r) {
                self.parent.refresh()
            });

            $("#modal_retry_job").modal("hide");
            form.reset()
        }
              
        // Searching in history (rate-limited in decleration)
        self.searchTerm.subscribe(function() {
            // If the refresh-rate is high we do a forced refresh
            if(parseInt(self.parent.refreshRate()) >2 ) {
                self.parent.refresh();
            }
            // Go back to page 1
            if(self.pagination.currentPage() != 1) {
                self.pagination.moveToPage(1);
            }
        })
        
        // Clear searchterm
        self.clearSearchTerm = function(objModel, event) {
            // Was it escape key or click?
            if(event.type == 'mousedown' || (event.keyCode && event.keyCode == 27)) {
                self.searchTerm('');
                self.parent.refresh();
            }
            // Need to return true to allow typing
            return true;
        }
        
        // Toggle showing failed
        self.toggleShowFailed = function() {
            self.showFailed(!self.showFailed())
            // Force refresh
            self.parent.refresh()
        }

        // Empty history options
        self.emptyHistory = function() {
            $("#modal_purge_history").modal('show');

            // After click
            $('#modal_purge_history .modal-body .btn').on('click', function(event) {
                // Only remove failed
                if(this.id == 'history_purge_failed') {
                    del_files = 0;
                    value = 'failed';
                }
                // Also remove files
                if(this.id == 'history_purgeremove_failed') {
                    del_files = 1;
                    value = 'failed';
                }
                // Remove completed
                if(this.id == 'history_purge_completed') {
                    del_files = 0;
                    value = 'completed';
                }

                // Call API and close the window
                callAPI({
                    mode: 'history',
                    name: 'delete',
                    value: value,
                    del_files: del_files
                }).then(function(response) {
                    if(response.status) {
                        self.parent.refresh();
                        $("#modal_purge_history").modal('hide');
                    }
                });
            });
        };
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
        self.nzo_id = '';
        self.updateAllHistory = false;
        self.historyStatus = ko.mapping.fromJS(data);
        self.status = ko.observable();
        self.action_line = ko.observable();
        self.script_line = ko.observable();
        self.fail_message = ko.observable();
        self.completed = ko.observable();
        self.canRetry = ko.observable();

        self.updateFromData = function(data) {
            // Fill all the basic info
            self.nzo_id = data.nzo_id;
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
        self.failed = ko.computed(function() {
            return self.status() === 'Failed';
        });

        // Waiting?
        self.processingWaiting = ko.computed(function() {
            return(self.status() == 'Queued')
        })

        // Processing or done?
        self.processingDownload = ko.computed(function() {
            var status = self.status();
            return(status === 'Extracting' || status === 'Moving' || status === 'Verifying' || status === 'Running' || status == 'Repairing')
        })

        // Format status text
        self.statusText = ko.computed(function() {
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

        // Format completion time
        self.completedOn = ko.computed(function() {
            return displayDateTime(self.completed(), parent.parent.dateFormat(), 'X')
        });

        // Re-try button
        self.retry = function() {
            // Set JOB-id
            $('#modal_retry_job input[name="retry_job_id"]').val(self.nzo_id)
                // Open modal
            $('#modal_retry_job').modal("show")
        };

        // Update information only on click
        self.updateAllHistoryInfo = function(data, event) {
            // Update all info
            self.updateAllHistory = true;
            parent.parent.refresh()

            // Update link
            setTimeout(function() {
                // Update it after the update of the info! Othwerwise it gets overwritten
                $(event.currentTarget).parent().find('.history-status-modallink a').click(function() {
                    // Info in modal
                    $('#history_script_log .modal-body').load($(event.currentTarget).parent().find('.history-status-modallink a').attr('href'), function(result) {
                        // Set title and then remove it
                        $('#history_script_log .modal-title').text($(this).find("h3").text())
                        $(this).find("h3, title").remove()
                        $('#history_script_log').modal({
                            show: true
                        });
                    });
                    return false;
                })
            }, 250)

            // Try to keep open
            keepOpen(event.target)
        }

        // Delete button
        self.deleteSlot = function(item, event) {
            if(!self.parent.parent.confirmDeleteHistory() || confirm(glitterTranslate.removeDow1)) {
                callAPI({
                    mode: 'history',
                    name: 'delete',
                    del_files: 1,
                    value: self.nzo_id
                }).then(function(response) {
                    if(response.status) {
                        // Fade and remove
                        $(event.currentTarget).parent().parent().fadeOut(fadeOnDeleteDuration, function() {
                            self.parent.historyItems.remove(self);
                            self.parent.parent.refresh();
                        })
                    }
                });
            }
        };

        // User voting
        self.setUserVote = function(item, event) {
            // Send vote
            callAPI({
                mode: 'queue',
                name: 'rating',
                type: 'vote',
                setting: $(event.target).val(),
                value: self.nzo_id
            }).then(function(response) {
                // Update all info
                self.updateAllHistory = true;
                self.parent.parent.refresh()
            })
        }

        // User rating
        self.setUserRating = function(item, event) {
            // Audio or video
            var changeWhat = 'audio';
            if($(event.target).attr('name') == 'ratings-video') {
                changeWhat = 'video';
            }

            // Only on user-event, not the auto-fired ones
            if(!event.originalEvent) return;

            // Send vote
            callAPI({
                mode: 'queue',
                name: 'rating',
                type: changeWhat,
                setting: $(event.target).val(),
                value: self.nzo_id
            }).then(function(response) {
                // Update all info
                self.updateAllHistory = true;
            })
        }

        // User comment
        self.setUserReport = function(form) {
            // What are we reporting?
            var userReport = $(form).find('input[name="rating_flag"]:checked').val();
            var userDetail = '';

            // Anything selected?
            if(!userReport) {
                alert(glitterTranslate.noSelect)
                return;
            }

            // Extra info?
            if(userReport == 'comment') userDetail = $(form).find('input[name="ratings-report-comment"]').val();
            if(userReport == 'other') userDetail = $(form).find('input[name="ratings-report-other"]').val();

            // Exception for servers
            if(userReport == 'expired') {
                // Which server?
                userDetail = $(form).find('select[name="ratings-report-expired-server"]').val();

                // All?
                if(userDetail == "") {
                    // Loop over all servers
                    $.each(parent.parent.servers, function(index, server) {
                        // Set timeout because simultanious requests don't work (yet)
                        setTimeout(function() {
                            submitUserReport(server.name)
                        }, index * 1500)
                    })

                } else {
                    // Just the one server
                    submitUserReport(userDetail)
                }
            } else {
                submitUserReport(userDetail)
            }

            // After all, close it
            form.reset();
            $(form).parent().parent().dropdown('toggle');
            alert(glitterTranslate.sendThanks)

            function submitUserReport(theDetail) {
                // Send note
                return callAPI({
                    mode: 'queue',
                    name: 'rating',
                    type: 'flag',
                    setting: userReport,
                    detail: theDetail,
                    value: self.nzo_id
                })
            }

            return false
        }

        // Update now
        self.updateFromData(data);
    }

    // For the file-list
    function Fileslisting(parent) {
        var self = this;
        self.parent = parent;
        self.fileItems = ko.observableArray([]);
        self.modalNZBId = ko.observable();
        self.modalTitle = ko.observable();
        self.modalPassword = ko.observable();
        self.modalProgressColor = ko.observable(false);

        // Load the function and reset everything
        self.loadFiles = function(queue_item) {
            // Update
            self.currentItem = queue_item;
            self.fileItems.removeAll()
            self.triggerUpdate()

            // Get pasword self.currentItem title
            passwordSplit = self.currentItem.name().split(" / ")

            // Has SAB already detected its encrypted? Then there will be 3x /
            passwordSplitExtra = 0;
            if(passwordSplit.length == 3 || passwordSplit[0] == 'ENCRYPTED') {
                passwordSplitExtra = 1;
            }

            // Set files & title
            self.modalNZBId(self.currentItem.id)
            self.modalTitle(passwordSplit[0 + passwordSplitExtra])
            self.modalPassword(passwordSplit[1 + passwordSplitExtra])
            
            // Set color in case we are still checking
            if(self.currentItem.status() == 'Checking') {
                self.modalProgressColor(true)
            }

            // Hide ok button and reset
            $('#modal_item_filelist .glyphicon-floppy-saved').hide()
            $('#modal_item_filelist .glyphicon-lock').show()
            $('#modal_item_files input[type="checkbox"]').prop('checked', false)

            // Show
            $('#modal_item_files').modal('show');

            // Stop updating on closing of the modal
            $('#modal_item_files').on('hidden.bs.modal', function() {
                self.removeUpdate();
            })
        }

        // Trigger update
        self.triggerUpdate = function() {
            // Call API
            callAPI({
                mode: 'get_files',
                value: self.currentItem.id,
                limit: 5
            }).then(function(response) {
                // When there's no files left we close the modal and the update will be stopped
                // For example when the job has finished downloading
                if(response.files.length === 0) {
                    $('#modal_item_files').modal('hide');
                    return;
                }

                // ID's
                var itemIds = $.map(self.fileItems(), function(i) {
                    return i.filename();
                });
                var newItems = [];

                // Go over them all
                $.each(response.files, function(index, slot) {
                    var existingItem = ko.utils.arrayFirst(self.fileItems(), function(i) {
                        return i.filename() == slot.filename;
                    });

                    if(existingItem) {
                        existingItem.updateFromData(slot);
                        itemIds.splice(itemIds.indexOf(slot.filename), 1);
                    } else {
                        // Add files item
                        newItems.push(new FileslistingModel(self, slot));
                    }
                })

                // Add new ones in 1 time instead of every single push
                if(newItems.length > 0) {
                    ko.utils.arrayPushAll(self.fileItems(), newItems);
                    self.fileItems.valueHasMutated();
                }

                // Check if we show/hide completed
                if(localStorageGetItem('showCompletedFiles') == 'No') {
                    $('.item-files-table tr:not(.files-sortable)').hide();
                    $('#filelist-showcompleted').removeClass('hoverbutton')
                }

                // Refresh with same as rest
                self.setUpdate()
            })
        }

        // Set update         
        self.setUpdate = function() {
            self.updateTimeout = setTimeout(function() {
                self.triggerUpdate()
            }, parent.refreshRate() * 1000)
        }

        // Remove the update
        self.removeUpdate = function() {
            clearTimeout(self.updateTimeout)
        }

        // Move in sortable
        self.move = function(e) {
            // How much did we move?
            var nrMoves = e.sourceIndex - e.targetIndex;
            var direction = (nrMoves > 0 ? 'Up' : 'Down')

            // We have to create the data-structure before, to be able to use the name as a key
            var dataToSend = {};
            dataToSend[e.item.nzf_id()] = 'on';
            dataToSend['session'] = apiKey;
            dataToSend['action_key'] = direction;
            dataToSend['action_size'] = Math.abs(nrMoves);

            // Activate with this weird URL "API"
            callSpecialAPI("nzb/" + self.currentItem.id + "/bulk_operation", dataToSend)
        };

        // Remove selected files
        self.removeSelectedFiles = function() {
            // We have to create the data-structure before, to be able to use the name as a key
            var dataToSend = {};
            dataToSend['session'] = apiKey;
            dataToSend['action_key'] = 'Delete';

            // Get all selected ones
            $('.item-files-table input:checked:not(:disabled)').each(function() {
                // Add this item
                dataToSend[$(this).prop('name')] = 'on';
            })

            // Activate with this weird URL "API"
            callSpecialAPI("nzb/" + self.currentItem.id + "/bulk_operation", dataToSend).then(function() {
                $('.item-files-table input:checked:not(:disabled)').parents('tr').fadeOut(fadeOnDeleteDuration)
            })

        }

        // For changing the passwords
        self.setNzbPassword = function() {
            // Activate with this weird URL "API"
            callSpecialAPI("nzb/" + self.currentItem.id + "/save", {
                name: self.modalTitle(),
                password: $('#nzb_password').val()
            }).then(function() {
                $('#modal_item_filelist .glyphicon-floppy-saved').show()
                $('#modal_item_filelist .glyphicon-lock').hide()
            })
            return false;
        }
    }

    // Indiviual file models
    function FileslistingModel(parent, data) {
        var self = this;
        // Define veriables
        self.filename = ko.observable();
        self.nzf_id = ko.observable();
        self.file_age = ko.observable();
        self.mb = ko.observable();
        self.percentage = ko.observable();
        self.canChange = ko.computed(function() {
            return self.nzf_id() != undefined;
        })

        // For selecting range
        self.checkSelectRange = function(data, event) {
            if(event.shiftKey) {
                checkShiftRange('.item-files-table input:not(:disabled)')
            }
            return true;
        }

        // Update internally
        self.updateFromData = function(data) {
            self.filename(data.filename)
            self.nzf_id(data.nzf_id)
            self.file_age(data.age)
            self.mb(data.mb)
            self.percentage(fixPercentages((100 - (data.mbleft / data.mb * 100)).toFixed(0)));
        }

        // Update now
        self.updateFromData(data);
    }

    // Model for pagination, since we use it multiple times
    function paginationModel(parent) {
        var self = this;

        // Var's
        self.nrPages = ko.observable(0);
        self.currentPage = ko.observable(1);
        self.currentStart = ko.observable(0);
        self.allpages = ko.observableArray([]).extend({
            rateLimit: 50
        });

        // Has pagination
        self.hasPagination = ko.computed(function() {
            return self.nrPages() > 1;
        })

        // Subscribe to number of items
        parent.totalItems.subscribe(function() {
            // Update
            self.updatePages();
        })

        // Subscribe to changes of pagination limit
        parent.paginationLimit.subscribe(function(newValue) {
            self.updatePages();
            self.moveToPage(self.currentPage());
        })

        // Easy handler for adding a page-link
        self.addPaginationPageLink = function(pageNr) {
            // Return object for adding
            return {
                page: pageNr,
                isCurrent: pageNr == self.currentPage(),
                isDots: false,
                onclick: function(data) {
                    self.moveToPage(data.page);
                }
            }
        }

        // Easy handler to add dots
        self.addDots = function() {
            return {
                page: '...',
                isCurrent: false,
                isDots: true,
                onclick: function() {}
            }
        }

        self.updatePages = function() {
            // Empty it
            self.allpages.removeAll();

            // How many pages do we need?
            if(parent.totalItems() <= parent.paginationLimit()) {
                // Empty it
                self.nrPages(1)

                // Reset all to make sure we see something
                self.currentPage(1);
                self.currentStart(0);
            } else {
                // Calculate number of pages needed
                newNrPages = Math.ceil(parent.totalItems() / parent.paginationLimit())
                
                // Make sure the current page still exists
                if(self.currentPage() > newNrPages) {
                    self.moveToPage(newNrPages);
                    return;
                }

                // All the cases
                if(newNrPages > 7) {
                    // Do we show the first ones 
                    if(self.currentPage() < 5) {
                        // Just add the first 4
                        $.each(new Array(5), function(index) {
                            self.allpages.push(self.addPaginationPageLink(index + 1))
                        })
                        // Dots
                        self.allpages.push(self.addDots())
                        // Last one
                        self.allpages.push(self.addPaginationPageLink(newNrPages))
                    } else {
                        // Always add the first 
                        self.allpages.push(self.addPaginationPageLink(1))
                            // Dots
                        self.allpages.push(self.addDots())

                        // Are we near the end?
                        if((newNrPages - self.currentPage()) < 4) {
                            // We add the last ones
                            $.each(new Array(5), function(index) {
                                self.allpages.push(self.addPaginationPageLink((index - 4) + (newNrPages)))
                            })
                        } else {
                            // We are in the center so display the center 3
                            $.each(new Array(3), function(index) {
                                self.allpages.push(self.addPaginationPageLink(self.currentPage() + (index - 1)))
                            })

                            // Dots
                            self.allpages.push(self.addDots())
                                // Last one
                            self.allpages.push(self.addPaginationPageLink(newNrPages))
                        }
                    }
                } else {
                    // Just add them
                    $.each(new Array(newNrPages), function(index) {
                        self.allpages.push(self.addPaginationPageLink(index + 1))
                    })
                }

                // Change of number of pages?
                if(newNrPages != self.nrPages()) {
                    // Update
                    self.nrPages(newNrPages);
                }
            }
        }

        // Update on click
        self.moveToPage = function(page) {
            // Update page and start
            self.currentPage(page)
            self.currentStart((page - 1) * parent.paginationLimit())
            // Re-paginate
            self.updatePages();
            // Force full update
            parent.parent.refresh();
        }
    }

    // GO!!!
    ko.applyBindings(new ViewModel(), document.getElementById("sabnzbd"));
});

/***
    GENERAL FUNCTIONS
***/
// Function to fix percentages
function fixPercentages(intPercent) {
    // Skip NaN's
    if(isNaN(intPercent))
        intPercent = 0;
    return Math.floor(intPercent || 0) + '%';
}

// Function to re-write 0:09:21 to 9:21
function rewriteTime(timeString) {
    var timeSplit = timeString.split(/:/);
    var hours = parseInt(timeSplit[0]);
    var minutes = parseInt(timeSplit[1]);
    var seconds = parseInt(timeSplit[2]);

    // Fix seconds
    if(seconds < 10) seconds = "0" + seconds;

    // With or without leading 0?
    if(hours == 0) {
        // Output
        return minutes + ":" + seconds
    }

    // Fix minutes if more than 1 hour
    if(minutes < 10) minutes = "0" + minutes;

    // Regular
    return hours + ':' + minutes + ':' + seconds;
}

// How to display the date-time?
function displayDateTime(inDate, outFormat, inFormat) {
    // What input?
    if(inDate == '') {
        var theMoment = moment()
    } else {
        var theMoment = moment(inDate, inFormat)
    }
    // Special format or regular format?
    if(outFormat == 'fromNow') {
        return theMoment.fromNow()
    } else {
        return theMoment.format(outFormat)
    }
}

// Keep dropdowns open
function keepOpen(thisItem) {
    // Onlick so it works for the dynamic items!
    $(thisItem).siblings('.dropdown-menu').children().click(function(e) {
        // Not for links
        if(!$(e.target).is('a')) {
            e.stopPropagation();
        }
    });
    // Add possible tooltips
    if(!isMobile) $(thisItem).siblings('.dropdown-menu').children('[data-toggle="tooltip"]').tooltip({ trigger: 'hover', container: 'body' })
}

// Check all functionality
function checkAllFiles(objCheck) {
    // Check for main-page or file-list modal?
    if($(objCheck).prop('name') == 'multieditCheckAll') {
        // Is checked himself?
        if($(objCheck).prop('checked')) {
            // (Un)check all in Queue by simulating click, this also fires the knockout-trigger!
            $('.queue-table input[name="multiedit"]').filter(":not(:checked):visible").trigger("click")
        } else {
            // Uncheck all checked ones and fires event
            $('.queue-table input[name="multiedit"]').filter(":checked:visible").trigger("click")
        }

    } else {
        // (Un)check all in file-list
        $('#modal_item_files input').filter(":checkbox:not(:disabled):visible").prop('checked', $(objCheck).prop('checked'))
    }
}

// Shift-range functionality for checkboxes
function checkShiftRange(strCheckboxes) {
    // Get them all
    var arrAllChecks = $(strCheckboxes);
    // Get index of the first and last
    var startCheck = arrAllChecks.index($(strCheckboxes + ':checked:first'));
    var endCheck = arrAllChecks.index($(strCheckboxes + ':checked:last'));
    // Everything in between click it to trigger addMultiEdit
    arrAllChecks.slice(startCheck, endCheck).filter(':not(:checked)').trigger('click')
}

// Hide completed files in files-modal
function hideCompletedFiles() {
    if($('#filelist-showcompleted').hasClass('hoverbutton')) {
        // Hide all
        $('.item-files-table tr:not(.files-sortable)').hide();
        $('#filelist-showcompleted').removeClass('hoverbutton')
        // Set storage
        localStorageSetItem('showCompletedFiles', 'No')
    } else {
        // show all
        $('.item-files-table tr:not(.files-sortable)').show();
        $('#filelist-showcompleted').addClass('hoverbutton')
        // Set storage
        localStorageSetItem('showCompletedFiles', 'Yes')
    }
}
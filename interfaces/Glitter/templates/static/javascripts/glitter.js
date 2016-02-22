/******
        
        Glitter V1
        By Safihre (2015) - safihre@sabnzbd.org
        
        Code extended from Shiny-template
        Code examples used from Knockstrap-template

********/
var fadeOnDeleteDuration = 400; // ms after deleting a row
var isMobile = (/android|webos|iphone|ipad|ipod|blackberry|iemobile|opera mini/i.test(navigator.userAgent.toLowerCase()));

// To avoid problems when localStorage is disabled
var hasLocalStorage = true;
function localStorageSetItem(varToSet, valueToSet) { try { return localStorage.setItem(varToSet, valueToSet); } catch(e) { hasLocalStorage = false; } }
function localStorageGetItem(varToGet) { try { return localStorage.getItem(varToGet); } catch(e) {  hasLocalStorage = false; } }

/**
    GLITTER CODE
**/
$(function() {
    'use strict';
    /**
        Base variables and functions
    **/

    // For mobile we disable zoom while a modal is being opened 
    // so it will not zoom unnecessarily on the modal
    if(isMobile) {
        $('.modal').on('show.bs.modal', function() {
            $('meta[name="viewport"]').attr('content', 'width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no');
        });
        
        // Restore on modal-close. Need timeout, otherwise it doesn't work
        $('.modal').on('hidden.bs.modal', function() {
            setTimeout(function() {
                $('meta[name="viewport"]').attr('content', 'width=device-width, initial-scale=1');
            },500);
        });
    }

    // Force compact mode as fast as possible
    if(localStorageGetItem('displayCompact') === 'true') {
        // Add extra class
        $('body').addClass('container-compact')
    }
    
    // Basic API-call
    function callAPI(data) {
        // Fill basis var's
        data.output = "json";
        data.apikey = apiKey;
        var ajaxQuery = $.ajax({
            url: "./tapi",
            type: "GET",
            cache: false,
            data: data,
            timeout: 10000 // Wait a little longer on mobile connections
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

        // Set status varibales
        self.isRestarting = ko.observable(false);
        self.useGlobalOptions = ko.observable(true).extend({ persist: 'useGlobalOptions' });
        self.refreshRate = ko.observable(1).extend({ persist: 'pageRefreshRate' });
        self.dateFormat = ko.observable('DD/MM/YYYY HH:mm').extend({ persist: 'pageDateFormat' });
        self.displayCompact = ko.observable(false).extend({ persist: 'displayCompact' });
        self.confirmDeleteQueue = ko.observable(true).extend({ persist: 'confirmDeleteQueue' });
        self.confirmDeleteHistory = ko.observable(true).extend({ persist: 'confirmDeleteHistory' });
        self.extraColumn = ko.observable('').extend({ persist: 'extraColumn' });
        self.hasStatusInfo = ko.observable(false); // True when we load it
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
        self.speedLimitText = ko.pureComputed(function() {
            // Set?
            if(!self.bandwithLimit()) return;
            
            // The text 
            var bandwithLimitText = self.bandwithLimit().replace(/[^a-zA-Z]+/g, '');
            
            // Only the number
            var speedLimitNumber = (parseInt(self.bandwithLimit()) * (self.speedLimit() / 100));
            
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
        self.speedText = ko.pureComputed(function() {
            return self.speed() + ' ' + (self.speedMetrics[self.speedMetric()] ? self.speedMetrics[self.speedMetric()] : "KB/s");
        });

        // Dynamic icon
        self.SABIcon = ko.pureComputed(function() {
            if(self.downloadsPaused()) {
                return './staticcfg/ico/faviconpaused.ico';
            } else {
                return './staticcfg/ico/favicon.ico';
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

            // Paused?
            self.downloadsPaused(response.queue.paused);

            // Finish action. Replace null with empty
            self.onQueueFinish(response.queue.finishaction ? response.queue.finishaction : '');

            // Disk sizes
            self.diskSpaceLeft1(response.queue.diskspace1_norm)

            // Same sizes? Then it's all 1 disk!
            if(response.queue.diskspace1 != response.queue.diskspace2) {
                self.diskSpaceLeft2(response.queue.diskspace2_norm)
            }
            
            // Did we exceed the space?
            self.diskSpaceExceeded1(parseInt(response.queue.mbleft)/1024 > parseInt(response.queue.diskspace1))
            self.diskSpaceExceeded2(parseInt(response.queue.mbleft)/1024 > parseInt(response.queue.diskspace2))

            // Quota
            self.quotaLimit(response.queue.quota)
            self.quotaLimitLeft(response.queue.left_quota)

            // System load
            self.systemLoad(response.queue.loadavg)

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
            // Clear previous timeout and set a new one to prevent double-calls
            clearTimeout(self.interval);
            self.interval = setTimeout(self.refresh, parseInt(self.refreshRate()) * 1000);
            
            /**
                Limited refresh
            **/
            // Only update the title when page not visible
            if(!pageIsVisible) {
                // Request new title 
                callSpecialAPI('./queue/', {}).done(function(data) {
                    // Split title & speed
                    var dataSplit = data.split('|||');

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
                Do first load with start-data
                Only works when the server knows the settings!
            **/
            if(glitterPreLoadHistory && self.useGlobalOptions()) {
                self.updateQueue(glitterPreLoadQueue);
                self.updateHistory(glitterPreLoadHistory);
                glitterPreLoadQueue = undefined;
                glitterPreLoadHistory = undefined;
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
            });
            // History
            callAPI({
                mode: "history",
                search: self.history.searchTerm(),
                failed_only: self.history.showFailed()*1,
                start: self.history.pagination.currentStart(),
                limit: parseInt(self.history.paginationLimit())
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
            // At least 3 charaters
            if(newValue.length < 3) {
                $('#customPauseOutput').text('').data('time', 0)
                $('#modal_custom_pause .btn-default').addClass('disabled')
                return;
            }
            
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

        // Clear warnings through this special URL..
        self.clearWarnings = function() {
            // Activate
            callSpecialAPI("./status/clearwarnings").done(self.refresh)
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
            // Ignore updates before the page is done
            if(!self.hasStatusInfo()) return;
            
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
            showNotification('.main-notification-box-uploading', 0, 1)
            self.addNZBFromFile($(form.nzbFile)[0].files[0]);

            // After that, hide and reset
            $("#modal-add-nzb").modal("hide");
            form.reset()
            $('#nzbname').val('')
            $('.btn-file em').html(glitterTranslate.chooseFile + '&hellip;')
        }
        // From URL
        self.addNZBFromURL = function(form) {
            // Anything?
            if(!$(form.nzbURL).val()) {
                $(form.nzbURL).attr('style', 'border-color: red !important')
                setTimeout(function() { $(form.nzbURL).css('border-color', '') }, 2000)
                return false;
            }

            // Add 
            callAPI({
                mode: "addurl",
                name: $(form.nzbURL).val(),
                nzbname: $('#nzbname').val(),
                cat: $('#modal-add-nzb select[name="Category"]').val() == '' ? 'Default' : $('#modal-add-nzb select[name="Category"]').val(),
                script: $('#modal-add-nzb select[name="Post-processing"]').val() == '' ? 'Default' : $('#modal-add-nzb select[name="Post-processing"]').val(),
                priority: $('#modal-add-nzb select[name="Priority"]').val() == '' ? -100 : $('#modal-add-nzb select[name="Priority"]').val(),
                pp: $('#modal-add-nzb select[name="Processing"]').val() == '' ? -1 : $('#modal-add-nzb select[name="Processing"]').val()
            }).then(function(r) {
                // Hide and reset/refresh
                self.refresh()
                $("#modal-add-nzb").modal("hide");
                form.reset()
                $('#nzbname').val('')
            });

        }
        // From the upload or filedrop
        self.addNZBFromFile = function(file) {
            // Adding a file happens through this special function
            var data = new FormData();
            data.append("name", file);
            data.append("mode", "addfile");
            data.append("nzbname", $('#nzbname').val());
            data.append("cat", $('#modal-add-nzb select[name="Category"]').val() == '' ? 'Default' : $('#modal-add-nzb select[name="Category"]').val()); // Default category
            data.append("script", $('#modal-add-nzb select[name="Post-processing"]').val() == '' ? 'Default' : $('#modal-add-nzb select[name="Post-processing"]').val()); // Default script
            data.append("priority", $('#modal-add-nzb select[name="Priority"]').val() == '' ? -100 : $('#modal-add-nzb select[name="Priority"]').val()); // Default priority
            data.append("pp", $('#modal-add-nzb select[name="Processing"]').val() == '' ? -1 : $('#modal-add-nzb select[name="Processing"]').val()); // Default post-processing options
            data.append("apikey", apiKey);
            // Add 
            $.ajax({
                url: "./tapi",
                type: "POST",
                cache: false,
                processData: false,
                contentType: false,
                data: data
            }).then(function(r) {
                // Hide notification
                hideNotification('.main-notification-box-uploading')
                // Refresh
                self.refresh();
            });

        }

        // Load status info
        self.loadStatusInfo = function(item, event) {
            // Hide tooltips (otherwise they stay forever..)
            $('#options-status [data-tooltip="true"]').tooltip('hide')

            // Reset if not called from a function
            if(item) {
                self.hasStatusInfo(false)
            }
            
            // Full refresh? Only on click and for the status-screen
            var statusFullRefresh = (event != undefined) && $('#options-status').hasClass('active');
            var strStatusUrl = statusFullRefresh ? './status/' : './status/?skip_dashboard=1';

            // Load the custom status info
            callSpecialAPI(strStatusUrl).then(function(data) {
                // Parse JSON
                var parsedJSON = ko.utils.parseJson(data);
                
                // Making the new objects
                self.statusInfo.status = ko.mapping.fromJS(parsedJSON.status);
                
                // Only when we do full refresh we have dashboard-info
                if(statusFullRefresh) self.statusInfo.dashboard = ko.mapping.fromJS(parsedJSON.dashboard);

                // Only now we can subscribe to the log-level-changes!
                self.statusInfo.status.loglevel.subscribe(function(newValue) {
                    // Update log-level
                    callSpecialAPI('./status/change_loglevel', {
                        loglevel: newValue
                    });
                })
                
                // Show again
                self.hasStatusInfo(true)

                // Add tooltips again
                if(!isMobile) $('#modal-options [data-tooltip="true"]').tooltip({ trigger: 'hover', container: 'body' })
            });
        }

        // Do a disk-speedtest
        self.testDiskSpeed = function() {
            // Hide tooltips (otherwise they stay forever..)
            $('#options-status [data-tooltip="true"]').tooltip('hide')
            // Hide before running the test
            self.hasStatusInfo(false)
            // Run it and then display it
            callSpecialAPI('./status/dashrefresh').then(function() {
                self.loadStatusInfo(true, true)
            })
        }

        // Unblock server
        self.unblockServer = function(servername) {
            callSpecialAPI("./status/unblock_server", {
                server: servername
            }).then(function() {
                $("#modal-options").modal("hide");
            })
        }

        // Refresh connections page
        var connectionRefresh
        $('.nav-tabs a[href="#options_connections"]').on('shown.bs.tab', function() {
            connectionRefresh = setInterval(function() {
                // Check if still visible
                if(!$('#options_connections').is(':visible') && connectionRefresh) {
                    // Stop refreshing
                    clearInterval(connectionRefresh)
                    return
                }
                // Only when we show them
                if(self.showActiveConnections()) {
                    console.log(Date.now())
                    self.loadStatusInfo()
                    // Trick to force the interface to refresh
                    self.hasStatusInfo(false)
                    self.hasStatusInfo(true)
                }
            }, self.refreshRate() * 1000)
        })

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
                name: $("<div/>").html(folder.folder()).text()
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
                showNotification('.main-notification-box-removing-multiple', 0, self.statusInfo.status.folders().length)
                // Delete them all
                callSpecialAPI("./status/delete_all").then(function() {
                    // Remove notifcation and update screen
                    hideNotification(true)
                    self.loadStatusInfo(true, true)
                })
            }     
        }

        self.displayCompact.subscribe(function() {
            $('body').toggleClass('container-compact')
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
            callSpecialAPI("./config/restart")

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
            callSpecialAPI("./config/repair").then(function() {
                hideNotification(true)
            })
        }
        // Force disconnect
        self.forceDisconnect = function() {
            // Show notification
            showNotification('.main-notification-box-disconnect', 3000)
            // Call API
            callSpecialAPI("./status/disconnect").then(function() {
                $("#modal-options").modal("hide");
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
            if(self.statusInfo.status.folders().length >= 3 && orphanMsg) {
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
            return (self.pagination.hasPagination() || self.searchTerm())
        })
        
        // Searching in queue (rate-limited in decleration)
        self.searchTerm.subscribe(function() {
            // If the refresh-rate is high we do a forced refresh
            if(parseInt(self.parent.refreshRate()) > 2 ) {
                self.parent.refresh();
            }
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
                        $('.delete input:checked').parents('tr').fadeOut(fadeOnDeleteDuration, function() {
                            self.parent.refresh();
                        })
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
        self.isGrabbing = ko.observable(data.status == 'Grabbing')
        self.totalMB = ko.observable(parseFloat(data.mb));
        self.remainingMB = ko.observable(parseFloat(data.mbleft));
        self.avg_age = ko.observable(data.avg_age)
        self.missing = ko.observable(data.missing)
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
        self.rating_avg_video = ko.observable(false)
        self.rating_avg_audio = ko.observable(false)
        
        // Color of the progress bar
        self.progressColor = ko.computed(function() {
            // Checking
            if(self.status() == 'Checking') {
                return '#58A9FA'
            }
            // Check for missing data, the value is arbitrary!
            if(self.missing() > 50) {
                return '#F8A34E'
            }
            // Set to grey, only when not Force download
            if((self.parent.parent.downloadsPaused() && self.priority() != 2) || self.pausedStatus()) {
                return '#B7B7B7'
            }
            // Nothing
            return '';
        });
        
        // MB's and percentages
        self.downloadedMB = ko.computed(function() {
            return(self.totalMB() - self.remainingMB()).toFixed(0);
        });
        self.percentageRounded = ko.pureComputed(function() {
            return fixPercentages(((self.downloadedMB() / self.totalMB()) * 100).toFixed(2))
        })
        self.progressText = ko.pureComputed(function() {
            return self.downloadedMB() + " MB / " + (self.totalMB() * 1).toFixed(0) + " MB";
        })
        
        // Texts
        self.missingText= ko.pureComputed(function() {
            // Check for missing data, the value is arbitrary!
            if(self.missing() > 50) {
                return self.missing() + ' ' + glitterTranslate.misingArt
            }
            return;
        })
        self.statusText = ko.computed(function() {
            // Checking
            if(self.status() == 'Checking') {
                return glitterTranslate.checking
            }
            // Pausing status
            if((self.parent.parent.downloadsPaused() && self.priority() != 2) || self.pausedStatus()) {
                return glitterTranslate.paused;
            }
            // Just the time
            return rewriteTime(self.timeLeft());
        });
        
        // Extra queue column
        self.extraText = ko.pureComputed(function() {
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
            return;
        })

        // Every update
        self.updateFromData = function(data) {
            // Update job info
            self.name($.trim(data.filename));
            self.password(data.password);
            self.index(data.index);
            self.status(data.status)
            self.isGrabbing(data.status == 'Grabbing')
            self.totalMB(parseFloat(data.mb));
            self.remainingMB(parseFloat(data.mbleft));
            self.avg_age(data.avg_age)
            self.missing(data.missing)
            self.category(data.cat);
            self.priority(parent.priorityName[data.priority]);
            self.script(data.script);
            self.unpackopts(parseInt(data.unpackopts)) // UnpackOpts fails if not parseInt'd!
            self.pausedStatus(data.status == 'Paused');
            self.timeLeft(data.timeleft);

            // If exists, otherwise false
            if(data.rating_avg_video !== undefined) {
                self.rating_avg_video(data.rating_avg_video === 0 ? '-' : data.rating_avg_video);
                self.rating_avg_audio(data.rating_avg_audio === 0 ? '-' : data.rating_avg_audio);
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
            if(!item.script()) return;
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
            if(item.status() == 'Fetching') return
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

    /**
        Model for the whole History with all its items
    **/
    function HistoryListModel(parent) {
        var self = this;
        self.parent = parent;

        // Variables
        self.historyItems = ko.observableArray([])
        self.showFailed = ko.observable(false);
        self.isLoading = ko.observable(false).extend({ rateLimit: 100 });
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
            
            // For new items
            var newItems = [];                                    
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
                    newItems.push(new HistoryModel(self, slot));
                }
            });
            
            // Remove all items
            if(itemIds.length == self.paginationLimit()) {
                // Replace it, so only 1 Knockout DOM-update!
                self.historyItems(newItems);
                newItems = [];
            } else {
                // Remove the un-used ones
                $.each(itemIds, function() {
                    var id = this.toString();
                    self.historyItems.remove(ko.utils.arrayFirst(self.historyItems(), function(i) {
                        return i.historyStatus.nzo_id() == id;
                    }));
                });
            }
            
            // Add new ones
            if(newItems.length > 0) {
                ko.utils.arrayPushAll(self.historyItems, newItems);
                self.historyItems.valueHasMutated();
                
                // Only now sort so newest on top. completed is updated every time while download is waiting
                // so doing the sorting every time would cause it to bounce around
                self.historyItems.sort(function(a, b) {
                    return a.historyStatus.completed() > b.historyStatus.completed() ? -1 : 1;
                });

                // We also check if it might be in the Multi-edit
                if(self.parent.queue.multiEditItems().length > 0) {
                    $.each(newItems, function() {
                        var currentItem = this;
                        self.parent.queue.multiEditItems.remove(function(inList) { return inList.id == currentItem.nzo_id; })
                    })
                }
            }

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
        });

        // Retry a job
        self.retryJob = function(form) {
            // Adding a extra retry file happens through this special function
            var data = new FormData();
            data.append("nzbfile", $(form.nzbFile)[0].files[0]);
            data.append("job", $('#modal-retry-job input[name="retry_job_id"]').val());
            data.append("password", $('#retry_job_password').val());
            data.append("session", apiKey);

            // Add 
            $.ajax({
                url: "./retry_pp",
                type: "POST",
                cache: false,
                processData: false,
                contentType: false,
                data: data
            }).then(self.parent.refresh);

            $("#modal-retry-job").modal("hide");
            $('.btn-file em').html(glitterTranslate.chooseFile + '&hellip;')
            form.reset()
        }
              
        // Searching in history (rate-limited in decleration)
        self.searchTerm.subscribe(function() {
            // If the refresh-rate is high we do a forced refresh
            if(parseInt(self.parent.refreshRate()) > 2 ) {
                self.parent.refresh();
            }
            // Go back to page 1
            if(self.pagination.currentPage() != 1) {
                self.pagination.moveToPage(1);
            }
        })
        
        // Clear searchterm
        self.clearSearchTerm = function(data, event) {
            // Was it escape key or click?
            if(event.type == 'mousedown' || (event.keyCode && event.keyCode == 27)) {
                // Set the loader so it doesn't flicker and then switch
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
        
        // Toggle showing failed
        self.toggleShowFailed = function(data, event) {
            // Set the loader so it doesn't flicker and then switch
            self.isLoading(true)
            self.showFailed(!self.showFailed())
            // Forde hide tooltip so it doesn't linger
            $('#history-options a').tooltip('hide')
            // Force refresh
            self.parent.refresh()
        }

        // Empty history options
        self.emptyHistory = function(data, event) {
            // Make sure no flickering
            self.isLoading(true)
            
            // What event?
            var whatToRemove = $(event.target).data('action');
            var del_files, value;
            
            // Purge failed
            if(whatToRemove == 'history-purge-failed') {
                del_files = 0;
                value = 'failed';
            }
            // Also remove files
            if(whatToRemove == 'history-purgeremove-failed') {
                del_files = 1;
                value = 'failed';
            }
            // Remove completed
            if(whatToRemove == 'history-purge-completed') {
                del_files = 0;
                value = 'completed';
            }
            // Remove the ones on this page
            if(whatToRemove == 'history-purge-page') {
                // List all the ID's
                var strIDs = '';
                $.each(self.historyItems(), function(index) {
                    strIDs = strIDs + this.nzo_id + ',';
                })
                // Send the command
                callAPI({
                    mode: 'history',
                    name: 'delete',
                    del_files: 1,
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
                value: value,
                del_files: del_files
            }).then(function() {
                self.parent.refresh();
                $("#modal-purge-history").modal('hide');
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
        self.nzo_id = data.nzo_id;
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
            return(self.status() == 'Queued')
        })

        // Processing or done?
        self.processingDownload = ko.pureComputed(function() {
            var status = self.status();
            return(status === 'Extracting' || status === 'Moving' || status === 'Verifying' || status === 'Running' || status == 'Repairing')
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

        // Format completion time
        self.completedOn = ko.pureComputed(function() {
            return displayDateTime(self.completed(), parent.parent.dateFormat(), 'X')
        });

        // Re-try button
        self.retry = function() {
            // Set JOB-id
            $('#modal-retry-job input[name="retry_job_id"]').val(self.nzo_id)
            // Open modal
            $('#modal-retry-job').modal("show")
        };

        // Update information only on click
        self.updateAllHistoryInfo = function(data, event) {
            // Show
            self.hasDropdown(true);
            
            // Update all info
            self.updateAllHistory = true;
            parent.parent.refresh();

            // Try to keep open
            keepOpen(event.target)
        }
        
        // Use KO-afterRender to add the click-functionality always
        self.addHistoryStatusStuff = function(item) {
            $(item).find('.history-status-modallink a').click(function(e) {
                // Modal or 'More' click?
                if($(this).is('.history-status-more')) {
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

        // Delete button
        self.deleteSlot = function(item, event) {
            // Are we not still processing?
            if(item.processingDownload() || item.processingWaiting()) return false;
            
            // Confirm?
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
                            // Make sure no flickering (if there are more items left) and then remove
                            self.parent.isLoading(self.parent.totalItems() > 1)
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
                callAPI({
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
    }

    // For the file-list
    function Fileslisting(parent) {
        var self = this;
        self.parent = parent;
        self.fileItems = ko.observableArray([]);

        // Need to reserve these names to be overwritten
        self.filelist_name = ko.observable();
        self.filelist_password = ko.observable();

        // Load the function and reset everything
        self.loadFiles = function(queue_item) {
            // Update
            self.currentItem = queue_item;
            self.fileItems.removeAll()
            self.triggerUpdate() 

            // Update name/password
            self.filelist_name(self.currentItem.name())
            self.filelist_password(self.currentItem.password())

            // Hide ok button and reset
            $('#modal-item-filelist .glyphicon-floppy-saved').hide()
            $('#modal-item-filelist .glyphicon-lock').show()
            
            // Set state of the check-all
            setCheckAllState('#modal-item-files .multioperations-selector input[type="checkbox"]', '#modal-item-files .files-sortable input')

            // Show
            $('#modal-item-files').modal('show');

            // Stop updating on closing of the modal
            $('#modal-item-files').on('hidden.bs.modal', function() {
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
                    $('#modal-item-files').modal('hide');
                    return;
                }

                // Go over them all
                var newItems = [];
                $.each(response.files, function(index, slot) {
                    // Existing or updating?
                    var existingItem = ko.utils.arrayFirst(self.fileItems(), function(i) {
                        return i.filename() == slot.filename;
                    });

                    if(existingItem) {
                        // We skip queued files!
                        // They cause problems because they can have the same filename
                        // as files that we do want to be updated.. The slot.id is not unique!
                        if(slot.status == "queued") return false;
                        
                        // Update the rest
                        existingItem.updateFromData(slot);
                    } else {
                        // Add files item
                        newItems.push(new FileslistingModel(self, slot));
                    }
                })

                // Add new ones in 1 time instead of every single push
                if(newItems.length > 0) {
                    ko.utils.arrayPushAll(self.fileItems, newItems);
                    self.fileItems.valueHasMutated();
                }

                // Check if we show/hide completed
                if(localStorageGetItem('showCompletedFiles') == 'No') {
                    $('.item-files-table tr.files-done').hide();
                    $('#filelist-showcompleted').removeClass('hover-button')
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
        self.move = function(event) {
            // How much did we move?
            var nrMoves = event.sourceIndex - event.targetIndex;
            var direction = (nrMoves > 0 ? 'Up' : 'Down')

            // We have to create the data-structure before, to be able to use the name as a key
            var dataToSend = {};
            dataToSend[event.item.nzf_id()] = 'on';
            dataToSend['session'] = apiKey;
            dataToSend['action_key'] = direction;
            dataToSend['action_size'] = Math.abs(nrMoves);

            // Activate with this weird URL "API"
            callSpecialAPI("./nzb/" + self.currentItem.id + "/bulk_operation", dataToSend)
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
            callSpecialAPI("./nzb/" + self.currentItem.id + "/bulk_operation", dataToSend).then(function() {
                // Fade it out
                $('.item-files-table input:checked:not(:disabled)').parents('tr').fadeOut(fadeOnDeleteDuration, function() {
                    // Set state of the check-all
                    setCheckAllState('#modal-item-files .multioperations-selector input[type="checkbox"]', '#modal-item-files .files-sortable input')
                })
            })
        }

        // For changing the passwords
        self.setNzbPassword = function() {
            // Activate with this weird URL "API"
            callSpecialAPI("./nzb/" + self.currentItem.id + "/save", {
                name: self.currentItem.name(),
                password: $('#nzb_password').val()
            }).then(function() {
                // Refresh, reset and close
                parent.refresh()
                $('#modal-item-filelist .glyphicon-floppy-saved').show()
                $('#modal-item-filelist .glyphicon-lock').hide()
                $('#modal-item-files').modal('hide')
            })
            return false;
        }
        
        // Check all
        self.checkAllFiles = function(item, event) {
            // Get which ones we care about
            var allChecks = $('#modal-item-files .files-sortable input').filter(':not(:disabled):visible');
            
            // We need to re-evaltuate the state of this check-all
            // Otherwise the 'inderterminate' will be overwritten by the click event!
            setCheckAllState('#modal-item-files .multioperations-selector input[type="checkbox"]', '#modal-item-files .files-sortable input')
            
            // Now we can check what happend    
            if(event.target.indeterminate) {
                allChecks.filter(":checked").prop('checked', false)
            } else {
                // Toggle their state by a click
                allChecks.prop('checked', !event.target.checked)
                event.target.checked = !event.target.checked;
                event.target.indeterminate = false;
            }
            // Set state of all the check-all's
            setCheckAllState('#modal-item-files .multioperations-selector input[type="checkbox"]', '#modal-item-files .files-sortable input')
            return true;
        }
        
        // For selecting range and the check-all button
        self.checkSelectRange = function(data, event) {
            if(event.shiftKey) {
                checkShiftRange('#modal-item-files .files-sortable input:not(:disabled)')
            }
            // Set state of the check-all
            setCheckAllState('#modal-item-files .multioperations-selector input[type="checkbox"]', '#modal-item-files .files-sortable input')
            return true;
        }
    }

    // Indiviual file models
    function FileslistingModel(parent, data) {
        var self = this;
        // Define veriables
        self.filename = ko.observable(data.filename);
        self.nzf_id = ko.observable(data.nzf_id);
        self.file_age = ko.observable(data.age);
        self.mb = ko.observable(data.mb);
        self.percentage = ko.observable(fixPercentages((100 - (data.mbleft / data.mb * 100)).toFixed(0)));
        self.canselect = ko.observable(data.nzf_id !== undefined);
        self.isdone =  ko.observable(data.status == "finished");

        // Update internally
        self.updateFromData = function(data) {
            self.filename(data.filename)
            self.nzf_id(data.nzf_id)
            self.file_age(data.age)
            self.mb(data.mb)
            self.percentage(fixPercentages((100 - (data.mbleft / data.mb * 100)).toFixed(0)));
            self.canselect(data.nzf_id !== undefined)
            self.isdone(data.status == "finished")
        }
    }

    // Model for pagination, since we use it multiple times
    function paginationModel(parent) {
        var self = this;

        // Var's
        self.nrPages = ko.observable(0);
        self.currentPage = ko.observable(1);
        self.currentStart = ko.observable(0);
        self.allpages = ko.observableArray([]).extend({ rateLimit: 50 });

        // Has pagination
        self.hasPagination = ko.pureComputed(function() {
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
                var newNrPages = Math.ceil(parent.totalItems() / parent.paginationLimit())
                
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
    // Make sure we clicked the a and not the glyphicon/caret!
    if(!$(thisItem).is('a') && !$(thisItem).is('button')) {
        // Do it again on the parent
        keepOpen(thisItem.parentElement)
        return;
    }

    // Onlick so it works for the dynamic items!
    $(thisItem).siblings('.dropdown-menu').children().click(function(e) {
        // Not for links
        if(!$(e.target).is('a')) {
            e.stopPropagation();
        }
    });
    // Add possible tooltips
    if(!isMobile) $(thisItem).siblings('.dropdown-menu').children('[data-tooltip="true"]').tooltip({ trigger: 'hover', container: 'body' })
}

// Show history details
function showDetails(thisItem) {
    // Unfortunatly the .dropdown('toggle') doesn't work in this setup, so work-a-round

    // Open the details of this, or close it?
    if($(thisItem).parent().find('.delete>.dropdown').hasClass('open')) {
        // One click = close
        $(thisItem).parent().find('.delete>.dropdown>a').click()
    } else {
        // Needs timeout, otherwise it thinks its the 'close' click for some reason
        setTimeout(function() {
            $(thisItem).parent().find('.delete>.dropdown>a').click()
        },1)
    }
}

// Check all functionality
function checkAllFiles(objCheck, onlyCheck) {
    // Get which ones we care about
    var allChecks = $($(objCheck).data('checkrange')).filter(':not(:disabled):visible');
    
    // We need to re-evaltuate the state of this check-all
    // Otherwise the 'inderterminate' will be overwritten by the click event!
    setCheckAllState('#'+objCheck.id, $(objCheck).data('checkrange'))
    
    // Now we can check what happend    
    if(objCheck.indeterminate) {
        // Uncheck if we don't need trigger
        if(onlyCheck) {
            allChecks.filter(":checked").prop('checked', false)
        } else  {
            allChecks.filter(":checked").trigger("click")
        }
    } else {
        // Toggle their state by a click
        allChecks.trigger("click")
    }
}

// To update the check-all button nicely
function setCheckAllState(checkSelector, rangeSelector) {  
    // See how many are checked
    var allChecks = $(rangeSelector).filter(':not(:disabled):visible')
    var nrChecks = allChecks.filter(":checked");
    if(nrChecks.length === 0) {
        $(checkSelector).prop({'checked': false, 'indeterminate': false})
    } else if(nrChecks.length == allChecks.length) {
        $(checkSelector).prop({'checked': true, 'indeterminate': false})
    } else {
        $(checkSelector).prop({'checked': false, 'indeterminate': true})
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
    if($('#filelist-showcompleted').hasClass('hover-button')) {
        // Hide all
        $('.item-files-table tr.files-done').hide();
        $('#filelist-showcompleted').removeClass('hover-button')
        // Set storage
        localStorageSetItem('showCompletedFiles', 'No')
    } else {
        // show all
        $('.item-files-table tr.files-done').show();
        $('#filelist-showcompleted').addClass('hover-button')
        // Set storage
        localStorageSetItem('showCompletedFiles', 'Yes')
    }
}

// Show status modal and switch to orphaned jobs tab
function showOrphans() {
    $('a[href="#modal-options"]').click().parent().click(); 
    $('a[href="#options-orphans"]').click()
}

// Show notification
function showNotification(notiName, notiTimeout, fileCounter) {
    // Set uploadcounter if there is one
    $('.main-notification-box .main-notification-box-file-count').text(fileCounter)

    // Hide others, show the new one
    $('.main-notification-box>div').hide()
    $(notiName).css('display', 'inline')
    // Only fade in when hidden
    $('.main-notification-box:hidden').fadeIn()

    // Remove after timeout
    if(notiTimeout) {
        setTimeout(function() { 
            hideNotification(true); 
        }, notiTimeout)
    }
}

// Hide notification
function hideNotification(fadeItOut) {
    // Hide the box with or without effect
    if(fadeItOut) {
        $('.main-notification-box').fadeOut()
    } else {
        $('.main-notification-box').hide()
    }
    
}
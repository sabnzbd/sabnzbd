/******
        
        Glitter V1
        By Safihre (2015)
        
        Code extended from Shiny-template
        Code examples used from Knockstrap-template

********/

/**
    FIX for IE8 and below not having IndexOf for array's
**/
if (!Array.prototype.indexOf) {
	Array.prototype.indexOf = function(elt /*, from*/ ) {
		var len = this.length >>> 0;
		var from = Number(arguments[1]) || 0;
		from = (from < 0) ? Math.ceil(from) : Math.floor(from);
		if (from < 0) from += len;
		for (; from < len; from++) {
			if (from in this && this[from] === elt) return from;
		}
		return -1;
	};
}

/**
    GLITTER CODE
**/
$(function() {
    // Set base variables
    var numPerPageQueue = $.cookie('queuePaginationLimit') ? $.cookie('queuePaginationLimit')  : 20;
    var numPerPageHistory = $.cookie('historyPaginationLimit') ? $.cookie('historyPaginationLimit')  : 5;
    var fadeOnDeleteDuration = 400; // ms after deleting a row
	var sparkline_config = {
		width:'150px',
        height: '32px',
		fillColor: '#9DDB72',
		spotColor: false,
		minSpotColor: false,
		maxSpotColor: false,
		lineColor: '#AAFFAA',
		disableTooltips: true,
		disableHighlight: true,
		highlightLineColor: '#FFFFFF',
		highlightSpotColor: false,
		chartRangeMin: 0
	};

    // Basic API-call
	function callAPI( data ) {
		data.output = "json";
		data.apikey = apiKey;
		var ajaxQuery = $.ajax({
			url: "tapi",
			type: "GET",
			cache: false,
			data: data
		});

		return $.when( ajaxQuery );
	}
    // Special API call
    function callSpecialAPI(url, data) {
        data.output = "json";
		data.apikey = apiKey;
		var ajaxQuery = $.ajax({
			url: url,
			type: "GET",
			cache: false,
			data: data
		});

		return $.when( ajaxQuery );
    }
    
   	function ViewModel() {
	    // Initialize models
		var self = this;
		self.queue = new QueueListModel(this);
		self.history = new HistoryListModel(this);
        self.filelist = new Fileslisting(this);

        // Set information varibales
        
        self.isRestarting      = ko.observable(false);
        self.refreshRate       = ko.observable($.cookie('pageRefreshRate') ? $.cookie('pageRefreshRate')  : 1)
        self.title             = ko.observable()
        self.hasStatusInfo     = ko.observable(false); // True when we load it
		self.speed             = ko.observable(0);
		self.speedMetric       = ko.observable();
        self.bandwithLimit     = ko.observable(false);
		self.speedLimit        = ko.observable(false).extend( { rateLimit: 200 } );
        self.speedLimitInt     = ko.observable(false); // We need the 'internal' counter so we don't trigger the API all the time
        self.downloadsPaused   = ko.observable(false);
		self.mainPauseStatus   = ko.observable();
		self.timeLeft          = ko.observable("0:00:00");
        self.diskSpaceLeft1    = ko.observable();
        self.diskSpaceLeft2    = ko.observable();
        self.queueDataLeft     = ko.observable();
        self.quotaLimit        = ko.observable();
        self.quotaLimitLeft    = ko.observable();
        self.nrWarnings        = ko.observable(0);
        self.allWarnings       = ko.observableArray([]).extend({ rateLimit: 50 });
        self.onQueueFinish     = ko.observable();
		self.speedMetrics      = { K: "KB/s", M: "MB/s", G: "GB/s" };
        self.speedHistory      = [];
        
        // Get the speed-limit
        callAPI({ mode:'get_config', section: 'misc', keyword: 'bandwidth_max' }).then(function(response) {
            // Set default value if none
            if(!response.config.misc.bandwidth_max) response.config.misc.bandwidth_max = false;
            self.bandwithLimit(response.config.misc.bandwidth_max);
        })
        
        // Make the speedlimit tekst
        self.speedLimitText = ko.computed(function() {
            // Set?
            if(!self.bandwithLimit()) return;
            
            // Only the number
            bandwithLimitNumber = parseInt(self.bandwithLimit());
            bandwithLimitNumber = (bandwithLimitNumber*(self.speedLimit()/100)).toFixed(1);
            
            // The text 
            bandwithLimitText = self.bandwithLimit().replace(/[^a-zA-Z]+/g, '');
            
            // Fix it for lower than 1MB/s
            if(bandwithLimitText == 'M' && bandwithLimitNumber < 1.025) {
                bandwithLimitText = 'K';
                bandwithLimitNumber = Math.round(bandwithLimitNumber * 1024);
            }
            // Show text
			return bandwithLimitNumber + ' ' + ( self.speedMetrics[ bandwithLimitText ] ? self.speedMetrics[ bandwithLimitText ] : "KB/s" );
		});
        
        // Dynamic speed text function
		self.speedText = ko.computed(function() {
			return self.speed() + ' ' + ( self.speedMetrics[ self.speedMetric() ] ? self.speedMetrics[ self.speedMetric() ] : "KB/s" );
		});
        
        // Dynamic icon
        self.SABIcon = ko.computed(function() {
            if(self.downloadsPaused()) {
                return './static/images/sabnzbdpluspaused.ico';
            } else {
                return './static/images/sabnzbdplus.ico';
            }
        })
        
        // Dynamic queue length check
        self.hasQueue = ko.computed(function() {
            return (self.queue.queueItems().length > 0)
        })
        
        // Dynamic history length check
        self.hasHistory = ko.computed( function() {
            // We also 'have history' if we can't find any results of the search
			return self.history.historyItems().length>0 || $('#history-table-searchbox').val() != ''
		});

        // Update main queue
		self.updateQueue = function( response ) {
			if(!self.queue.shouldUpdate()) return;
            
            // Make sure we are displaying the interface
            if(self.isRestarting() >= 1) {
                // Decrease the counter by 1
                // In case of restart (which takes time to fire) we count down
                // In case of re-connect after failure it counts from 1 so emmediate continuation
                self.isRestarting(self.isRestarting()-1);
                return;
            }
                
            /***
                Basic information
            ***/
            // Finish action
            self.onQueueFinish(response.queue.finishaction);
            
            // Paused?
            self.downloadsPaused(response.queue.paused);
			self.mainPauseStatus( self.downloadsPaused() ? "glyphicon-play" : "glyphicon-pause" );
      
            // Disk and queyesizes
            if(response.queue.mbleft > 0)
                self.queueDataLeft(Math.round(response.queue.mbleft))
            else
                self.queueDataLeft("")
            
            self.diskSpaceLeft1(parseFloat(response.queue.diskspace1).toFixed(1))
            
            // Same sizes? Then it's all 1 disk!
            if(response.queue.diskspace1 != response.queue.diskspace2)
                self.diskSpaceLeft2(parseFloat(response.queue.diskspace2).toFixed(1))

            // Quota
            self.quotaLimit(response.queue.quota)
            self.quotaLimitLeft(response.queue.left_quota)
            
            /***
                 Warnings
            ***/
            if(parseInt(response.queue.have_warnings) > self.nrWarnings()) {
                // Get all warnings
                callAPI( { mode:'warnings' } ).then( function( response ) {
                    // Reset it all
                    self.allWarnings.removeAll();
    				if( response ) {
    				    // Go over all warnings and add
    				    $.each(response.warnings, function(index, warning) {
    				        // Split warning into parts
    				        var warningSplit = warning.split(/\n/);

                            
                            // Reformat CSS label and date
				            var warningData = {
				                    index: index,
				                    type: warningSplit[1],
                                    text: warningSplit.slice(2).join(' '), // Recombine if multiple lines
                                    date: $.format.date(warningSplit[0], 'dd/MM/yy HH:mm'), 
				                    css: (warningSplit[1] == "ERROR" ? "danger" : warningSplit[1] == "WARNING" ? "warning" : "info"), 
                                    clear: self.clearWarnings
                                  };
			
    				        self.allWarnings.push(warningData)
    				    })
    				}
    			});
            }
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
			self.speed( parseFloat( speedSplit[0] ) );
			self.speedMetric( speedSplit[1] );

            // Add to sparkline
			if(self.speedHistory.length >= 50)
				self.speedHistory.shift();
			self.speedHistory.push( parseFloat( response.queue.kbpersec ) );

            // Anything to report?
            $('.sparkline').sparkline(self.speedHistory, sparkline_config);
                
            /***
                Speedlimit
            ***/
            // Nothing = 100%
            response.queue.speedlimit = response.queue.speedlimit=='' ? 100 : response.queue.speedlimit;
            
            // First load
            if(!self.speedLimitInt()) {
                // Set speedlimit from the 1st response
                self.speedLimitInt(response.queue.speedlimit)
                self.speedLimit(response.queue.speedlimit)
            } else {
                self.speedLimitInt(response.queue.speedlimit)
            }

            /***
                Download timing and pausing
            ***/
			timeString = response.queue.timeleft;
			if(timeString === '') {
                timeString = '0:00:00';
			} else {
                timeString = rewriteTime(response.queue.timeleft)
			}
			
            // Paused main queue
			if(self.downloadsPaused()) {
				if( response.queue.pause_int == '0' ) {
					timeString = 'Paused';
				} else {
					pauseSplit = response.queue.pause_int.split(/:/);
					seconds = parseInt(pauseSplit[0]) * 60 + parseInt(pauseSplit[1]);
					hours = Math.floor(seconds/3600);
					minutes = Math.floor((seconds -= hours * 3600) / 60);
					seconds -= minutes * 60;
					timeString = 'Paused (' + rewriteTime(hours + ":" + minutes + ":" + seconds) + ')';
				}
                
                // Add info about amount of download (if actually downloading)
                if(response.queue.slots.length > 0 && self.queueDataLeft() > 0) {
                    self.title(timeString + ' - ' + self.queueDataLeft() + ' MB left - SABnzbd')
                } else {
                    // Set title with pause information
                    self.title(timeString + ' - SABnzbd')
                }
            } else if(response.queue.slots.length > 0 && self.queueDataLeft() > 0) {
                // Set title only if we are actually downloading something..
                self.title(self.speedText() + ' - ' + self.queueDataLeft() + ' MB left - SABnzbd')
            } else {
                // Empty title
                self.title('SABnzbd')
            }

            // Save for timing box
			self.timeLeft( timeString );
            
            // Update queue rows
			self.queue.updateFromData( response.queue );
		}

        // Update history items
		self.updateHistory = function( response ) {
			if(!response) return;
			self.history.updateFromData( response.history );
		}

        // Refresh function
		self.refresh = function() {
            // Do requests for information
            // Catch the fail to display message
			callAPI( {  mode: "queue", 
                        start: self.queue.pagination.currentStart(), 
                        limit: self.queue.paginationLimit() } ).then(
                            self.updateQueue, 
                            function() { self.isRestarting(true)} 
                        );
			callAPI( {  mode: "history", 
                        search: $('#history-table-searchbox').val(),
                        start: self.history.pagination.currentStart(), 
                        limit: self.history.paginationLimit()} ).then( self.updateHistory );
		};

        // Set pause action on click of toggle
		self.pauseToggle = function() {
			self.mainPauseStatus( self.downloadsPaused() ? "glyphicon-play" : "glyphicon-pause" );
			callAPI( { mode: ( self.downloadsPaused() ? "resume" : "pause" ) } ).then( self.refresh );
			self.downloadsPaused(!self.downloadsPaused());
		}

        // Pause timer
		self.pauseTime = function(e, b) {
			pauseDuration = $(b.currentTarget).data( 'time' );
			self.mainPauseStatus( "glyphicon-pause" );
			callAPI( { mode: 'config', name: 'set_pause', value: pauseDuration } );
			self.downloadsPaused(true);
		};
        
        
        
        // Clear warnings through this weird URL..
        self.clearWarnings = function() {
            if ( !confirm( "Are you sure you want to clear all warnings?" ) )
				return;
            // Activate
            $.ajax({
    			url: "status/clearwarnings", 
    			type: "GET", 
    			cache: false, 
    			data: { session: apiKey }
    		})
        }
        
        // Update on speed-limit change
		self.speedLimit.subscribe( function( newValue ) {
            // Only on new load
            if(!self.speedLimitInt()) return;
            
            // Update
            if(self.speedLimitInt() != newValue) {
                callAPI( { mode:"config", name:"speedlimit", value:newValue} )
            }
		} );
        
        // Clear speedlimit
        self.clearSpeedLimit = function() {
            self.speedLimit(100);
        }
        
        // Shutdown options
        self.setQueueFinish = function(data, event) {
            // Get action from event and call API
            callAPI({mode:'queue', name:'change_complete_action', value: $(event.currentTarget).data('action') })
        }
        
        // Update refreshrate
        self.refreshRate.subscribe( function( newValue ) {
            clearInterval(self.interval)
            self.interval = setInterval( self.refresh, parseInt(newValue)*1000 );
            $.cookie('pageRefreshRate', parseInt(newValue), { expires: 365 });
        })
        
        /***
             Add NZB's
        ***/
        // NOTE: Adjusted from Knockstrap template
        self.addNZBFromFileForm = function(form) {
            self.addNZBFromFile($(form.nzbFile)[0].files[0]);
            form.reset()
        }
        self.addNZBFromURL = function(form) {
            // Add 
            callAPI({   mode:       "addid", 
                        name:       $(form.nzbURL).val(), 
                        cat:        $('#modal_add_nzb select[name="Category"]').val()=='' ? 'Default' : $('#modal_add_nzb select[name="Category"]').val(), 
                        script:     $('#modal_add_nzb select[name="Post-processing"]').val()=='' ? 'Default' : $('#modal_add_nzb select[name="Post-processing"]').val(),  
                        priority:   $('#modal_add_nzb select[name="Priority"]').val()=='' ? -100 : $('#modal_add_nzb select[name="Priority"]').val(),  
                        pp:         $('#modal_add_nzb select[name="Processing"]').val()=='' ? -1 : $('#modal_add_nzb select[name="Processing"]').val(), 
            }).then(function(r) { self.refresh() });
            // Hide and reset/refresh
            $("#modal_add_nzb").modal("hide");
            form.reset()
        }
        self.addNZBFromFile = function(file) {
            // Adding a file happens through this special function
            var data = new FormData();
    		data.append("name",       file);
    		data.append("mode",       "addfile");
    		data.append("cat",        $('#modal_add_nzb select[name="Category"]').val()=='' ? 'Default' : $('#modal_add_nzb select[name="Category"]').val());    // Default category
    		data.append("script",     $('#modal_add_nzb select[name="Post-processing"]').val()=='' ? 'Default' : $('#modal_add_nzb select[name="Post-processing"]').val()); // Default script
    		data.append("priority",   $('#modal_add_nzb select[name="Priority"]').val()=='' ? -100 : $('#modal_add_nzb select[name="Priority"]').val());  // Default priority
    		data.append("pp",         $('#modal_add_nzb select[name="Processing"]').val()=='' ? -1 : $('#modal_add_nzb select[name="Processing"]').val());          // Default post-processing options
            data.append("apikey",     apiKey);
            // Add 
            $.ajax({    url: "tapi", 
                        type: "POST", 
                        cache: false, 
                        processData: false, 
                        contentType: false, 
                        data: data }).then(function(r) { self.refresh() });
            // Hide
            $("#modal_add_nzb").modal("hide");
        }
        
        // Load status info
        self.loadStatusInfo = function() {
            // Reset
            self.hasStatusInfo(false)
                    
            // Load the custom status info
            $.ajax({ 
                url: "status/", 
                type: "GET", 
                cache: false }).then(function(data) { 
                    // Already exists?
                    if(self.hasStatusInfo()) {
                        ko.mapping.fromJS(JSON.parse(data), self.statusInfo);
                    } else {
                        self.statusInfo = ko.mapping.fromJS(JSON.parse(data));
                    }
                    // Show again
                    self.hasStatusInfo(true)
                    
                    // Add tooltips again
                    $('#modal_options [data-toggle="tooltip"]').tooltip()
                });
            
        }
        
        // Unblock server
        self.unblockServer = function(servername) {
            $.ajax({ url: "status/unblock_server", type: "GET", cache: false, data: { session: apiKey, server: servername } }).then(function() {$("#modal_options").modal("hide");}) 
        }
        
        // Abandoned folder processing
        self.folderProcess = function(e,b) {
            // Activate
            $.ajax({
    			url: "status/" + $(b.currentTarget).data('action'), 
    			type: "GET", 
    			cache: false, 
    			data: { 
                    session: apiKey,
                    name: $(b.currentTarget).data('folder') 
                }
    		}).then(function() {
                // Remove item and load status data
                $(b.currentTarget).parent().parent().fadeOut(fadeOnDeleteDuration /*, function() {self.loadStatusInfo()}*/)
                
    		})
        }
      
        // SABnzb options
        self.shutdownSAB = function() { 
            return confirm('Are you sure you want to shutdown SABnzbd?'); 
        }
        self.restartSAB = function() { 
             if(!confirm('Are you sure you want to restart SABnzbd?\nUse it when you think the program has a stability problem.\nDownloading will be paused before the restart and will resume afterwards.')) return;
             $.ajax({ url: "config/restart", type: "POST", cache: false, data: { session: apiKey } })
             
             // Set counter, we need at least 15 seconds
             self.isRestarting(Math.max(1, Math.floor(15/self.refreshRate())));
             // Force refresh in case of very long refresh-times
             if(self.refreshRate() > 30) { setTimeout(self.refresh, 30*1000) }
        }
        self.repairQueue = function() { 
            if(!confirm('The Repair button will restart SABnzbd and do a complete construction of the queue content, preserving already downloaded files. This will modify the queue order.')) return;
            $.ajax({ url: "config/repair", type: "POST", cache: false, data: { session: apiKey } }).then(function() {$("#modal_options").modal("hide");}) 
        }
        self.forceDisconnect = function() { 
            $.ajax({ url: "status/disconnect", type: "POST", cache: false, data: { session: apiKey } }).then(function() {$("#modal_options").modal("hide");}) 
        }
        
     
        // Set interval for refreshing queue
		self.interval = setInterval( self.refresh, parseInt(self.refreshRate())*1000 );
        // And refresh now!
        self.refresh()
        
        // Activate tooltips
        $('[data-toggle="tooltip"]').tooltip()
	}
    
   	function QueueListModel( parent ) {
        // Internal var's
		var self = this;
		this.parent = parent;
		var multiEditItems = [];
        
        // Because SABNZB returns the name, not the number...
        self.priorityName = []; 
    		self.priorityName["Force"] = 2; 
    		self.priorityName["High"] = 1; 
    		self.priorityName["Normal"] = 0; 
    		self.priorityName["Low"] = -1; 
    		self.priorityName["Stop"] = -4;
       	self.priorityOptions = ko.observableArray([
    		{ value: 2, name: "Force" },
    		{ value: 1, name: "High" },
    		{ value: 0, name: "Normal" },
    		{ value: -1, name: "Low" },
    		{ value: -4, name: "Stop" }]);
    	self.processingOptions = ko.observableArray([
    		{ value: 0, name: "Download" },
    		{ value: 1, name: "+Repair" },
    		{ value: 2, name: "+Unpack" },
    		{ value: 3, name: "+Delete" }]);
        
        // External var's
        self.queueItems      = ko.observableArray([]).extend({rateLimit: 50});
        self.totalItems      = ko.observable(0);
        self.isMultiEditing  = ko.observable(false);
        self.categoriesList  = ko.observableArray( [] );
        self.scriptsList     = ko.observableArray( [] );
        self.dragging        = false;
        self.paginationLimit = ko.observable(numPerPageQueue)
        self.pagination      = new paginationModel(self);

        // Don't update while dragging
		self.shouldUpdate    = function() { return !self.dragging; }
        self.dragStart       = function( e ) { self.dragging = true; }
        self.dragStop        = function( e ) { self.dragging = false; }

		self.updateFromData = function( data ) {
            // Get all ID's'
			var itemIds = $.map( self.queueItems(), function(i) { return i.id; } );
            
            // Set categories and scripts and limit
            self.scriptsList(data.scripts)
            self.categoriesList(data.categories)
            self.totalItems(data.noofslots);
            
            // Go over all items
			$.each( data.slots, function() {
				var item = this;
				var existingItem = ko.utils.arrayFirst( self.queueItems(), function( i ) { return i.id == item.nzo_id; } );

				if( existingItem ) {
					existingItem.updateFromData( item );
					itemIds.splice( itemIds.indexOf( item.nzo_id ), 1 );
				} else {
                    // Add new item
                    self.queueItems.push( new QueueModel( self, item ) );
				}
                // Sort by item
				self.queueItems.sort( function(a, b) { return a.index() < b.index() ? -1 : 1; } );	
			} );

			$.each(itemIds, function() {
				var id = this.toString();
				self.queueItems.remove( ko.utils.arrayFirst( self.queueItems(), function( i ) { return i.id == id; } ) );
			});
		};

        // Move in sortable
		self.move = function( e ) {
			var itemMoved = e.item;
			var itemReplaced = ko.utils.arrayFirst( self.queueItems(), function( i ) { return i.index() == e.targetIndex; } );

			itemMoved.index( e.targetIndex );
			itemReplaced.index( e.sourceIndex );

			callAPI( { mode: "switch", value: itemMoved.id, value2: e.targetIndex } ).then( function( r ) {
				if( r.position != e.targetIndex ) {
					itemMoved.index( e.sourceIndex );
					itemReplaced.index( e.targetIndex );
				}
			});
		};
        
        // Save pagination state
        self.paginationLimit.subscribe( function( newValue ) {
			numPerPageQueuem = newValue;
            $.cookie('queuePaginationLimit', numPerPageQueuem, { expires: 365 });
            self.parent.refresh();
		} );
        
        /***
            Multi-edit functions
        ***/
        self.showMultiEdit = function() { 
            // Update value
            self.isMultiEditing(!self.isMultiEditing()) 
            // Do update on close, to make sure it's all updated
            if(!self.isMultiEditing()) {
                self.parent.refresh()
            }
        }
        
        self.addMultiEdit = function(item, event) {
            // Add or remove from the list?
            if(event.currentTarget.checked) {
                // Add item
                multiEditItems.push(item)
                // Update them all
                self.doMultiEditUpdate();
            } else {
                // Go over them all to know which one to remove 
                $.each(multiEditItems, function(index) {
    				// Is this the one removed?
                    if(item.id == this.id) {
                        multiEditItems.splice(index,1)
                    }
    			});
            }
            
            return true;
        }
        
        // Do the actual multi-update immediatly
        self.doMultiEditUpdate = function() {
            // Retrieve the current settings
            newCat      = $('.multioperations-selector select[name="Category"]').val()
            newScript   = $('.multioperations-selector select[name="Post-processing"]').val()
            newPrior    = $('.multioperations-selector select[name="Priority"]').val() 
            newProc     = $('.multioperations-selector select[name="Processing"]').val()
            
            // List all the ID's
            strIDs = '';
            $.each(multiEditItems, function(index) {
                strIDs = strIDs + this.id + ',';
            })
            
            // What is changed?
            if(newCat != '')    { callAPI( { mode: 'change_cat', value: strIDs, value2: newCat } ) }
            if(newScript != '') { callAPI( { mode: 'change_script', value: strIDs, value2: newScript } )}
            if(newPrior != '')  { callAPI( { mode: 'queue', name:'priority', value: strIDs, value2: newPrior } ) }
            if(newProc != '')   { callAPI( { mode: 'change_opts', value: strIDs, value2: newProc } ) }
        }
        
        // Selete all selected
        self.doMultiDelete = function() {
            if ( !confirm( "Are you sure you want to remove these downloads?" ) ) return;
            
            // List all the ID's
            strIDs = '';
            $.each(multiEditItems, function(index) {
                strIDs = strIDs + this.id + ',';
            })
            
            // Remove
            callAPI( { mode: 'queue', name: 'delete', del_files: 1, value: strIDs } ).then( function( response ) {
				if( response.status ) {
                    $('.delete input:checked').parents('tr').fadeOut(fadeOnDeleteDuration, function() {
                        self.parent.refresh();
                    })
                }
            })
        }
        
        // On change of page we need to check all those that were in the list!
        self.queueItems.subscribe(function() {
            $.each(multiEditItems, function(index) {
                $('#multiedit_' + this.id).prop('checked', true);
            })   
        }, null, "arrayChange")
	}

	function QueueModel( parent, data ) {
		var self = this;
		this.parent = parent;

        // Define all knockout variables
        self.id;
		self.index = ko.observable();
		self.name = ko.observable();
        self.status = ko.observable(); 
        self.isGrabbing = ko.observable(false);
		self.totalMB = ko.observable(0);
		self.remainingMB = ko.observable(0);
		self.timeLeft = ko.observable();
        self.progressColor = ko.observable();
        self.missingText = ko.observable();
		self.category = ko.observable();
        self.script  = ko.observable();
		self.priority = ko.observable();
        self.unpackopts = ko.observable();
        self.editingName = ko.observable(false);
        self.nameForEdit = ko.observable();
		self.pausedStatus = ko.observable();
        self.rating_avg_video = ko.observable(false);
        self.rating_avg_audio = ko.observable(false);
        
        // Functional vars        
		self.downloadedMB = ko.computed( function() {
			return ( self.totalMB() - self.remainingMB() ).toFixed( 0 );
		}, this );

		self.percentage = ko.computed( function() {
			return ( ( self.downloadedMB() / self.totalMB() ) * 100 ).toFixed( 2 );
		}, this );
		
		self.percentageRounded = ko.computed( function() {
            return fixPercentages(self.percentage())
		}, this );

		self.progressText = ko.computed( function() {
			return self.downloadedMB() + " MB / " + (self.totalMB()*1).toFixed(0) + " MB";
		}, this );
        

        // Every update
		self.updateFromData = function( data ) {
            // General status
			self.id = data.nzo_id;
			if( data.status != 'Grabbing' ) {
				self.name($.trim(data.filename));
			} else {
				self.name('Grabbing...');
                self.isGrabbing(true)
                return; // Important! Otherwise cat/script/priority get magically changed!
            }

            // Set stats
            self.progressColor(''); // Reset
            self.status(data.status)
			self.totalMB(parseFloat(data.mb) );
			self.remainingMB(parseFloat(data.mbleft) );
			self.category(data.cat);
			self.priority(parent.priorityName[data.priority]);
            self.script(data.script);
			self.index(data.index);
            self.unpackopts(parseInt(data.unpackopts)) // UnpackOpts fails if not parseInt'd!
			self.pausedStatus(data.status == 'Paused');
            
            // If exists, otherwise false
            if(data.rating_avg_video !== undefined) {
                self.rating_avg_video( data.rating_avg_video === 0 ? '-' : data.rating_avg_video );
                self.rating_avg_audio( data.rating_avg_audio === 0 ? '-' : data.rating_avg_audio );
            }
            
            // Checking
            if(data.status == 'Checking') {
                self.progressColor('#58A9FA')
                self.timeLeft("Checking");
            }
            
            // Check for missing data, the value is arbitrary!
            if(data.missing > 50) {
                self.progressColor('#F8A34E');
                self.missingText(data.missing + ' missing articles')
            }
            
            // Set color   
			if( (self.parent.parent.downloadsPaused() && data.priority != 'Force') || self.pausedStatus() ) {
				self.timeLeft("Paused");
                self.progressColor('#B7B7B7');
			} else if(data.status != 'Checking') {
			 	self.timeLeft(rewriteTime(data.timeleft));
			}
		};

        // Pause individual download
		self.pauseToggle = function() {
			callAPI( { mode: 'queue', name: ( self.pausedStatus() ? 'resume' : 'pause' ), value: self.id } ).then(self.parent.parent.refresh);
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
                callAPI( { mode: 'queue', name: "rename", value: self.id, value2: newName } )
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
        self.changeCat          = function(itemObj) { callAPI( { mode: 'change_cat', value: itemObj.id, value2: itemObj.category() } )}
        self.changeScript       = function(itemObj) { callAPI( { mode: 'change_script', value: itemObj.id, value2: itemObj.script() } )}
        self.changeProcessing   = function(itemObj) { callAPI( { mode: 'change_opts', value: itemObj.id, value2: itemObj.unpackopts() } ) }
        self.changePriority     = function(itemObj) { 
            // Not if we are fetching extra blocks for repair!
            if(itemObj.status() == 'Fetching') return
            callAPI( { mode: 'queue', name:'priority', value: itemObj.id, value2: itemObj.priority() } 
        )}

        
        // Remove
        self.removeDownload = function(data, event) {
			if ( !confirm( "Are you sure you want to remove this download?" ) )	return;
			var itemToDelete = this;
			callAPI( { mode: 'queue', name: 'delete', del_files: 1, value: this.id } ).then( function( response ) {
				if( response.status ) {
				    // Fade and remove
                    $(event.currentTarget).parent().parent().fadeOut(fadeOnDeleteDuration, function() {
                        parent.queueItems.remove( itemToDelete );
                        self.parent.parent.refresh();
                    })
					
				}
			});
		};
        
        // Update
		self.updateFromData( data );
	}
    
   	function HistoryListModel( parent ) {
		var self = this;
		this.parent = parent;
        
        // Variables
		self.historyItems    = ko.observableArray( [] );
        self.hasScriptLines  = ko.observable(false);
        self.paginationLimit = ko.observable(numPerPageHistory);
        self.totalItems      = ko.observable(0);
        self.pagination      = new paginationModel(self);
      
        // Download history info
        self.downloadedToday = ko.observable();
        self.downloadedWeek  = ko.observable();
        self.downloadedMonth = ko.observable();
        self.downloadedTotal = ko.observable();

        
        // Update function for history list
		self.updateFromData = function( data ) {
            /***
                History list functions per item
            ***/
			var itemIds = $.map( self.historyItems(), function(i) { return i.historyStatus.nzo_id(); } );

			$.each( data.slots, function(index, slot) {
				var existingItem = ko.utils.arrayFirst( self.historyItems(), function( i ) { return i.historyStatus.nzo_id() == slot.nzo_id; } );

				if( existingItem ) {
					existingItem.updateFromData( slot );
					itemIds.splice( itemIds.indexOf( slot.nzo_id ), 1 );
				} else {
				    // Add history item
					self.historyItems.push( new HistoryModel( self, slot ) );
                    // Only now sort so newest on top
                    self.historyItems.sort( function( a, b ) { return a.historyStatus.completed() > b.historyStatus.completed() ? -1 : 1; } );
                }
			} );

            // Remove the un-used ones
			$.each( itemIds, function() {
				var id = this.toString();
				self.historyItems.remove( ko.utils.arrayFirst( self.historyItems(), function( i ) { return i.historyStatus.nzo_id() == id; } ) );
			} );
            
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
        self.paginationLimit.subscribe( function( newValue ) {
			numPerPageHistory = newValue;
            $.cookie('historyPaginationLimit', numPerPageHistory, { expires: 365 });
            self.parent.refresh();
		} );

        
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
                callAPI( { mode:'history', name:'delete', value:value, del_files:del_files } ).then( function( response ) {
    				if( response.status ) {
    				    self.parent.refresh();
    				    $("#modal_purge_history").modal('hide');
    				}
    			});
            });
        };
	}

	function HistoryModel( parent, data ) {
		var self = this;
		self.parent = parent;

        // We only update the whole set of information ONCE
        // If we update the full set every time it uses lot of CPU
        // The Status/Actionline/scriptline/completed we do update every time
        // When clicked on the more-info button we load the rest again
        self.historyStatus = ko.mapping.fromJS(data);   
        self.updateAllHistory = false;
        self.status = ko.observable();
        self.action_line = ko.observable();
        self.script_line = ko.observable();
        self.fail_message = ko.observable();
        self.completed = ko.observable();        

		self.updateFromData = function( data ) {       
            // Fill all the basic info
            self.status(data.status)
            self.action_line(data.action_line)
            self.script_line(data.script_line)
            self.fail_message(data.fail_message)
            self.completed(data.completed) 
            
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
        
        // Processing or done?
        self.processingDownload = ko.computed(function() {
            var status = self.status();
            return (status === 'Extracting' || status === 'Moving' || status === 'Verifying' || status === 'Running' || status == 'Repairing' || status == 'Queued')
        })

        // Quick function for the icon
		self.iconStatus = ko.computed(function() {
			var status = self.status();
     
			if(status === 'Completed')
				return 'glyphicon-ok';
			else if(status === 'Extracting' || status === 'Moving' || status === 'Verifying' || status === 'Running' || status == 'Repairing' || status == 'Queued')
				return 'glyphicon-refresh glyphicon-spin'; 
            
			return 'glyphicon-exclamation-sign';
		});

        // Format status text
		self.statusText = ko.computed(function() {
			if(self.action_line() !== '')
				return self.action_line();
			if(self.status() === 'Failed') // Failed
				return self.fail_message();
            if(self.status() === 'Queued')
                return 'Waiting';
            if(self.script_line() === '') // No script line
                return 'Completed'

			return self.script_line();
		});
        
        // Format completion time
        self.completedOn = ko.computed(function() {
            return $.format.date(parseInt(self.completed())*1000, 'dd/MM/yy HH:mm')
        });

        // Re-try button
		self.retry = function() {
			callAPI( {mode:'retry', value:self.historyStatus.nzo_id()} ).then(self.parent.parent.refresh);
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
                    $('#history_script_log .modal-body').load($(event.currentTarget).parent().find('.history-status-modallink a').attr('href'),function(result){
                	    $('#history_script_log').modal({show:true});
                	});
                    return false;
                })
            },250)
        }

        // Delete button
		self.deleteSlot = function(item, event) {
			if ( !confirm( "Are you sure you want to remove this download from history?" ) )
				return;

			callAPI( {mode:'history', name:'delete', del_files:1, value:self.historyStatus.nzo_id()} ).then( function(response) {
				if( response.status ) {
				    // Fade and remove
                    $(event.currentTarget).parent().parent().fadeOut(fadeOnDeleteDuration, function() {
                        self.parent.historyItems.remove(self);
	                    self.parent.parent.refresh();
                    })				    
					
				}
			});
		};

        // Update now
		self.updateFromData( data );
	}
    
    // For the file-list
    function Fileslisting( parent ) {
		var self = this;
		self.parent = parent;
        self.fileItems = ko.observableArray([]).extend({ rateLimit: 50 });
        self.modalNZBId = ko.observable();
        self.modalTitle = ko.observable();
        self.modalPassword = ko.observable();
        
        // Load the function and reset everything
        self.loadFiles = function(queue_item) {
            // Update
            self.currentItem = queue_item;
            self.fileItems.removeAll()
            self.triggerUpdate()
            
            // Get pasword self.currentItem title
            passwordSplit = self.currentItem.name().split(" / ")
            
            // Set files & title
            self.modalNZBId(self.currentItem.id)
            self.modalTitle(passwordSplit[0])
            self.modalPassword(passwordSplit[1])
            
            // Hide ok button and reset
            $('#modal_item_filelist .glyphicon-floppy-saved').hide()
            $('#modal_item_filelist .glyphicon-lock').show()
            $('#modal_item_files input[type="checkbox"]').prop('checked', false)
            
            // Show
            $('#modal_item_files').modal('show');
            
            // Stop updating on closing of the modal
            $('#modal_item_files').on('hidden.bs.modal', function () { self.removeUpdate(); }) 
        }

        // Trigger update
        self.triggerUpdate = function() {
            callAPI( { mode: 'get_files', value: self.currentItem.id, limit: 5 } ).then(function(response) {
                // When there's no files left we close the modal and the update will be stopped
                // For example when the job has finished downloading
                if(response.files.length === 0) {
                    $('#modal_item_files').modal('hide');
                    return;
                }
                
                // ID's
                var itemIds = $.map( self.fileItems(), function(i) { return i.filename(); } );
                
                // Go over them all
                $.each( response.files, function(index, slot) {
                    var existingItem = ko.utils.arrayFirst( self.fileItems(), function( i ) {  return i.filename() == slot.filename; } );
    
    				if( existingItem ) {
    					existingItem.updateFromData( slot );
                        itemIds.splice( itemIds.indexOf( slot.filename ), 1 );
    				} else {
    				    // Add files item
    					self.fileItems.push( new FileslistingModel( self, slot ) );
                    }    
                })
                
                // Check if we show/hide completed
                if($.cookie('showCompletedFiles') == 'No') {
                    $('.item-files-table tr:not(.files-sortable)').hide();
                    $('#filelist-showcompleted').removeClass('hoverbutton')
                }
                
                // Refresh with same as rest
                self.updateTimeout = setTimeout(function() {
                    self.triggerUpdate()
                }, parent.refreshRate()*1000)
            })
        }
        
        // Remove the update
        self.removeUpdate = function() {
            clearTimeout(self.updateTimeout)
        }
    
        
        // Move in sortable
		self.move = function( e ) {
            // How much did we move?
            var nrMoves = e.sourceIndex - e.targetIndex;
            var direction = (nrMoves > 0 ? 'Up' : 'Down')
            
            // Do it as much as need (UNTIL WE HAVE A GOOD API!)
            for(i = 1; i <= Math.abs(nrMoves); i++) {
                // We have to create the data-structure before, to be able to use the name as a key
                var dataToSend = {};
                dataToSend[e.item.nzf_id()] = 'on';
                dataToSend['session'] = apiKey;
                dataToSend['action_key'] = direction;
                // Activate with this weird URL "API"
                $.ajax({
        			url: "nzb/" + self.currentItem.id + "/bulk_operation", 
        			type: "POST", 
        			cache: false, 
        			data: dataToSend
        		})
            }
		};
        
        // Remove selected files
        self.removeSelectedFiles = function() {
            // We have to create the data-structure before, to be able to use the name as a key
            var dataToSend = {};
            dataToSend['session'] = apiKey;
            dataToSend['action_key'] = 'Delete';
            
            // Get all selected ones
            $('.item-files-table input:checked').each(function() {
                // Add this item
                dataToSend[$(this).prop('name')] = 'on';
            }) 
                
            // Activate with this weird URL "API"
            $.ajax({
    			url: "nzb/" + self.currentItem.id + "/bulk_operation", 
    			type: "POST", 
    			cache: false, 
    			data: dataToSend
    		}).then(function() {
                $('.item-files-table input:checked').parents('tr').fadeOut(fadeOnDeleteDuration)
    		})
            
        }
        
        // For changing the passwords
        self.setNzbPassword = function() {
            // Activate with this weird URL "API"
            $.ajax({
    			url: "nzb/" + self.currentItem.id + "/save", 
    			type: "POST", 
    			cache: false, 
    			data: { 
                    session: apiKey, 
                    name: self.modalTitle(),
                    password: $('#nzb_password').val() 
                }
    		}).then(function() {
                $('#modal_item_filelist .glyphicon-floppy-saved').show()
                $('#modal_item_filelist .glyphicon-lock').hide()
    		})
            return false;
        }
    }
    
    function FileslistingModel(parent, data) {
        var self = this;
        // Define veriables
        self.filename = ko.observable();
        self.nzf_id = ko.observable();
        self.file_age = ko.observable();
        self.percentage  = ko.observable();
        self.canChange = ko.computed(function() { return self.nzf_id()!=undefined; })
        self.filenameAndAge = ko.pureComputed(function() { 
            return self.filename() + ' <small>(' + self.file_age() + ')</small>';
        })
        
        // Update internally
        self.updateFromData = function(data) {
            self.filename(data.filename)
            self.nzf_id(data.nzf_id)
            self.file_age(data.age)
            self.percentage(fixPercentages((100-(data.mbleft/data.mb*100)).toFixed(0)));
        }
        
        // Update now
		self.updateFromData( data );
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
                newNrPages = Math.ceil(parent.totalItems()/parent.paginationLimit())
                
                // Make sure the current page still exists
                if(self.currentPage() > newNrPages) {
                    self.moveToPage(newNrPages);
                    return;
                }

                // All the cases
                if(newNrPages > 6 ) {
                    // Do we show the first ones 
                    if(self.currentPage() < 5) {
                        // Just add the first 4
                        $.each(new Array(5), function(index) {
                            self.allpages.push(self.addPaginationPageLink(index+1))
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
                                self.allpages.push(self.addPaginationPageLink((index-4)+(newNrPages)))
                            })
                        } else {
                            // We are in the center so display the center 3
                            $.each(new Array(3), function(index) {
                                self.allpages.push(self.addPaginationPageLink(self.currentPage()+(index-1)))
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
                        self.allpages.push(self.addPaginationPageLink(index+1))
                    })
                }

                // Change of number of pages?
                if(newNrPages != self.nrPages()) {
                    // Update
                    self.nrPages(newNrPages);
                    // Force full update
                    parent.parent.refresh();
                }
            }
        }
        
        // Update on click
        self.moveToPage = function(page) {
            // Update page and start
            self.currentPage(page)
            self.currentStart((page-1)*parent.paginationLimit())
            // Re-paginate
            self.updatePages();
            // Force full update
            parent.parent.refresh();
        }
    }

    // GO!!!
	ko.applyBindings( new ViewModel(), document.getElementById("sabnzbd") );
});

/***
    GENERAL FUNCTIONS
***/
// Function to fix percentages
function fixPercentages(intPercent) {
    // Skip NaN's
    if(isNaN(intPercent)) 
        intPercent = 0;
    return Math.floor( intPercent || 0 ) +'%';
}

// Function to re-write 0:09:21 to 9:21
function rewriteTime(timeString) {
    
    var timeSplit = timeString.split(/:/);

	var hours = parseInt(timeSplit[0]);
	var minutes = parseInt(timeSplit[1]);
	var seconds = parseInt(timeSplit[2]);
    
    // Fix seconds
    if(seconds < 10 ) seconds = "0" + seconds;
        
    // With or without leading 0?
    if(hours == 0) {
        // Output
        return minutes + ":" +seconds
    }
    
    // Fix minutes if more than 1 hour
    if(minutes < 10 ) minutes = "0" + minutes;
    
    // Regular
    return hours + ':' + minutes + ':' +seconds;
} 


// Keep dropdowns open
function keepOpen(thisItem) {
    // Onlick so it works for the dynamic items!
    $(thisItem).siblings('.dropdown-menu').find('input, select, span, div, td').click(function(e) {
        e.stopPropagation();
    });
}

// Check all functionality
function checkAllFiles(objCheck) {
    // Check or uncheck all?
    $('#modal_item_files input:checkbox:not(:disabled)').prop('checked', $(objCheck).prop('checked'))
}

// Hide completed files in files-modal
function hideCompletedFiles() {
    if($('#filelist-showcompleted').hasClass('hoverbutton')) {
        // Hide all
        $('.item-files-table tr:not(.files-sortable)').hide();
        $('#filelist-showcompleted').removeClass('hoverbutton')
        // Set cookie
        $.cookie('showCompletedFiles', 'No', { expires: 365 })
    } else {
        // show all
        $('.item-files-table tr:not(.files-sortable)').show();
        $('#filelist-showcompleted').addClass('hoverbutton')
        // Set cookie
        $.cookie('showCompletedFiles', 'Yes', { expires: 365 })
    }
}

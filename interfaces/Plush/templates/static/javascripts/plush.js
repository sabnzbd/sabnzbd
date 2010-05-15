// ***************************************************************
// Plush main code as follows, by pairofdimes (see LICENSE-CC.txt)

jQuery(function($){

	$.plush = {
		
		// ***************************************************************
		//	Plush defaults
		
		refreshRate:   			$.cookie('refreshRate')  ? $.cookie('refreshRate')  : 30,   // refresh rate in seconds
		queuePerPage:   		$.cookie('queuePerPage') ? $.cookie('queuePerPage') : 10,	// pagination - nzbs per page
		histPerPage:   			$.cookie('histPerPage')  ? $.cookie('histPerPage')  : 10,	// pagination - nzbs per page
		confirmDeleteQueue:		$.cookie('confirmDeleteQueue') 	 == 0 ? false : true,		// confirm queue nzb removal
		confirmDeleteHistory:	$.cookie('confirmDeleteHistory') == 0 ? false : true,		// confirm history nzb removal
		blockRefresh:			$.cookie('blockRefresh') 		 == 0 ? false : true,		// prevent refreshing when hovering queue
		
		
		// ***************************************************************
		//	$.plush.Init() -- initialize all the UI events

		Init : function() {
			$.plush.InitAddNZB();
			$.plush.InitMainMenu();
			$.plush.InitQueue();
			$.plush.InitHistory();
			$.plush.InitTooltips();
		}, // end $.plush.Init()


		// ***************************************************************
		//	$.plush.InitAddNZB() -- "Add NZB" Methods
			
		InitAddNZB : function() {
			// Fetch NZB by URL/Newzbin Report ID
			$('#addID').click(function(){ // also works when hitting enter because of <form>
				if ($('#addID_input').val()!='URL') {
					$.ajax({
						type: "POST",
						url: "tapi",
						data: {
							mode:	  'addid',
							name:	  $("#addID_input").val(),
							pp:		  $("#addID_pp").val(),
							script:   $("#addID_script").val(),
							cat:	  $("#addID_cat").val(),
							priority: $("#addID_priority").val(),
							apikey:	  $.plush.apikey
						},
						success: $.plush.RefreshQueue
					});
					$("#addID_input").val('');
				}
				return false; // aborts <form> submission
			});
			$('#addID_input').val('URL')
			.focus( function(){
				if ($(this).val()=="URL")
					$(this).val('');
			}).blur( function(){
				if (!$(this).val())
					$(this).val('URL');
			});

			// Upload NZB ajax with webtoolkit
			$('#uploadNZBFile').change( function(){ $('#uploadNZBForm').submit(); });
			$('#uploadNZBForm').submit( function(){
				return AIM.submit(this, {'onComplete': $.plush.RefreshQueue})
			});

			// Fetch Newzbin Bookmarks
			$('#fetch_newzbin_bookmarks').click(function(){
				$.ajax({
					type: "POST",
					url: "tapi",
					data: {mode:'newzbin', name:'get_bookmarks', apikey: $.plush.apikey},
					success: function(result){
						$.plush.RefreshQueue();
					}
				});
			});

		}, // end $.plush.InitAddNZB()

		
		// ***************************************************************
		//	$.plush.InitMainMenu() -- Main Menu Events
			
		InitMainMenu : function() {

			// Main menu -- uses jQuery hoverIntent
			$("#main_menu ul.sf-menu").superfish({
				autoArrows:	true,
	  			dropShadows: false
	  		});
	  		$("#queue-buttons ul").superfish({
	  		  autoArrows: false,
	  		  dropShadows: false
	  		});
			
			// Max Speed main menu input -- don't change value on refresh when focused
			$("#maxSpeed-option").focus(function(){ $.plush.focusedOnSpeedChanger = true; })
 								  .blur(function(){ $.plush.focusedOnSpeedChanger = false; });
			$("#maxSpeed-option").change( function() {	// works with hitting enter
				$.ajax({
					type: "POST",
					url: "tapi",
					data: {mode:'config', name:'set_speedlimit', value: $(this).val(), apikey: $.plush.apikey}
				});
			});
			
			// Refresh rate
			$("#refreshRate-option").val($.plush.refreshRate).change( function() {
				$.plush.refreshRate = $("#refreshRate-option").val();
				$.cookie('refreshRate', $.plush.refreshRate, { expires: 365 });
				$.plush.Refresh();
			});
			
			// Confirm Queue Deletions toggle
			$("#confirmDeleteQueue").attr('checked', $.plush.confirmDeleteQueue ).change( function() {
				$.plush.confirmDeleteQueue = $("#confirmDeleteQueue").attr('checked');
				$.cookie('confirmDeleteQueue', $.plush.confirmDeleteQueue ? 1 : 0, { expires: 365 });
			});
			
			// Confirm History Deletions toggle
			$("#confirmDeleteHistory").attr('checked', $.plush.confirmDeleteHistory ).change( function() {
				$.plush.confirmDeleteHistory = $("#confirmDeleteHistory").attr('checked');
				$.cookie('confirmDeleteHistory', $.plush.confirmDeleteHistory ? 1 : 0, { expires: 365 });
			});
			
			// Block Refreshes on Hover toggle
			$("#blockRefresh").attr('checked', $.plush.blockRefresh ).change( function() {
				$.plush.blockRefresh = $("#blockRefresh").attr('checked');
				$.cookie('blockRefresh', $.plush.blockRefresh ? 1 : 0, { expires: 365 });
			});
			
			// Sabnzbd shutdown
			$('#shutdown_sabnzbd').click( function(){
				if(confirm($('#shutdown_sabnzbd').attr('rel')))
					window.location='shutdown?session='+$.plush.apikey;
			});
			
			// Queue "Upon Completion" script
			$("#onQueueFinish-option").change( function() {
				$.ajax({
					type: "POST",
					url: "tapi",
					data: {mode:'queue', name:'change_complete_action', value: $(this).val(), apikey: $.plush.apikey}
				});
			});
					
			// Queue purge
			$('#queue_purge').click(function(event) {
				if(confirm($('#queue_purge').attr('rel'))){
					$.ajax({
						type: "POST",
						url: "tapi",
						data: {mode:'queue', name:'delete', value:'all', apikey: $.plush.apikey},
						success: $.plush.RefreshQueue
					});
				}
			});
			
			// Queue sort (6-in-1)
			$('#queue_sort_list .queue_sort').click(function(event) {
				var sort, dir;
				switch ($(this).attr('id')) {
					case 'sortAgeAsc':		sort='avg_age';	dir='asc';	break;
					case 'sortAgeDesc':		sort='avg_age';	dir='desc';	break;
					case 'sortNameAsc':		sort='name';	dir='asc';	break;
					case 'sortNameDesc':	sort='name';	dir='desc';	break;
					case 'sortSizeAsc':		sort='size';	dir='asc';	break;
					case 'sortSizeDesc':	sort='size';	dir='desc';	break;
				}
				$.ajax({
					type: "POST",
					url: "tapi",
					data: {mode:'queue', name:'sort', sort: sort, dir: dir, apikey: $.plush.apikey},
					success: $.plush.RefreshQueue
				});
			});
			
			// Queue pause intervals
			$('#set_pause_list .set_pause').click(function(event) {
				var minutes = $(event.target).attr('rel');
				if (minutes == "custom")
					minutes = prompt($(event.target).attr('title'));
				$.ajax({
					type: "POST",
					url: "tapi",
					data: {mode:'config', name:'set_pause', value: minutes, apikey: $.plush.apikey},
					success: $.plush.RefreshQueue
				});
			});
			
			// Manual refresh
			$('#manual_refresh_wrapper').click(function(e){
				// prevent button text highlighting
			    e.target.onselectstart = function() { return false; };
			    e.target.unselectable = "on";
			    e.target.style.MozUserSelect = "none";
			    //e.target.style.cursor = "default";

				$.plush.Refresh(true);
			});

		}, // end $.plush.InitMainMenu()
			
		
		// ***************************************************************
		//	$.plush.InitTooltips() -- title tootlips on hover

		InitTooltips : function() {
			// TO DO:
			//		clean up implementation, unfortunately was not built as a plugin
			//		fix glitching on superfish tooltips (#uploadTip doesn't work, #fetch_newzbin_bookmarks only works when hover from side)

			/*
			 * jQuery tooltips
			 * Version 1.1  (April 6, 2010)
			 * @requires jQuery v1.4.2+
			 * @author Karl Swedberg
			 *
			 * Dual licensed under the MIT and GPL licenses:
			 * http://www.opensource.org/licenses/mit-license.php
			 * http://www.gnu.org/licenses/gpl.html
			 *
			 */
  
			var $liveTip = $('<div id="livetip"></div>').hide().appendTo('body'),
			    $win = $(window),
			    showTip;

			var tip = {
			  title: '',
			  offset: 12,
			  delay: 0, 		// changed
			  position: function(event) {
			    var positions = {x: event.pageX, y: event.pageY};
			    var dimensions = {
			      x: [
			        $win.width(),
			        $liveTip.outerWidth()
			      ],
			      y: [
			        $win.scrollTop() + $win.height(),
			        $liveTip.outerHeight()
			      ]
			    };

			    for ( var axis in dimensions ) {

			      if (dimensions[axis][0] < dimensions[axis][1] + positions[axis] + this.offset) {
			        positions[axis] -= dimensions[axis][1] + this.offset;
			      } else {
			        positions[axis] += this.offset;
			      }

			    }

			    $liveTip.css({
			      top: positions.y,
			      left: positions.x
			    });
			  }
			};

			$('body').delegate('#time-left, #have_warnings, #explain-blockRefresh, #uploadTip, #fetch_newzbin_bookmarks, #pauseForPrompt, #pause_resume, #hist_purge, #queueTable td.download-title a, #queueTable td.options .icon_nzb_remove, #historyTable td.options .icon_nzb_remove, #historyTable td div.icon_history_verbose', 'mouseover mouseout mousemove', function(event) {
			  var link = this,
			      $link = $(this);

			  if (event.type == 'mouseover') {
			    tip.title = link.title;
			    link.title = '';

			    showTip = setTimeout(function() {

			      $link.data('tipActive', true);

			      tip.position(event);

			      $liveTip
			      .html('<div>' + tip.title + '</div>') //<div>' + link.href + '</div>')  	// changed
			      //.fadeOut(0)  															// changed
			      .show();//.fadeIn(200);  													// changed

			    }, tip.delay);
			  }

			  if (event.type == 'mouseout') {
			    link.title = tip.title || link.title;
			    if ($link.data('tipActive')) {
			      $link.removeData('tipActive');
			      $liveTip.hide();
			    } else {
			      clearTimeout(showTip);
			    }
			  }

			  if (event.type == 'mousemove' && $link.data('tipActive')) {
			    tip.position(event);
			  }
  
			});
		},


		// ***************************************************************
		//	$.plush.InitQueue() - Queue Events

		InitQueue : function() {
			
			// Pause/resume toggle (queue)
			$('#pause_resume').click(function(event) {
				if ( $(event.target).hasClass('sprite_q_pause_on') ) {
					$('#pause_resume').removeClass('sprite_q_pause_on').addClass('sprite_q_pause');
					$('#pause_int').html("");
					$.ajax({
						type: "POST",
						url: "tapi",
						data: {mode:'resume', apikey: $.plush.apikey}
					});
				} else {
					$('#pause_resume').removeClass('sprite_q_pause').addClass('sprite_q_pause_on');
					$('#pause_int').html("");
					$.ajax({
						type: "POST",
						url: "tapi",
						data: {mode:'pause', apikey: $.plush.apikey}
					});
				}
			});

			// Set queue per-page preference
			$("#queue-pagination-perpage").val($.plush.queuePerPage);
			$.plush.queuecurpage = 0; // default 1st page

			// Pagination per-page selection
			$("#queue-pagination-perpage").change(function(event){
				$.plush.queuecurpage = Math.floor($.plush.queuecurpage * $.plush.queuePerPage / $(event.target).val() );
				$.plush.queuePerPage = $(event.target).val();
				$.cookie('queuePerPage', $.plush.queuePerPage, { expires: 365 });
				$.plush.queueforcerepagination = true;
				$.plush.RefreshQueue();
			});
			
			// Skip queue refresh on mouseover
			$('#queue').hover(
				function(){ $.plush.skipRefresh=true; }, // over
				function(){ $.plush.skipRefresh=false; } // out
			);

			// refresh on mouseout after deletion
			$('#queue').hover(	// $.mouseout was triggering too often
				function(){}, // over
				function(){	  // out
					if ($.plush.pendingQueueRefresh) {
						$.plush.pendingQueueRefresh = false;
						$.plush.RefreshQueue();
					}
				}
			);
			
			// NZB pause/resume individual toggle
			$('#queueTable .nzb_status').live('click',function(event){
				var pid = $(this).parent().parent().attr('id');
				if ($(this).hasClass('sprite_ql_grip_queued_on')) {
					$(this).toggleClass('sprite_ql_grip_queued_on').toggleClass('sprite_ql_grip_paused_on');
					$.ajax({
						type: "POST",
						url: "tapi",
						data: {mode:'queue', name:'pause', value: pid, apikey: $.plush.apikey}
					});
				} else if ($(this).hasClass('sprite_ql_grip_active')) {
					$(this).toggleClass('sprite_ql_grip_active').toggleClass('sprite_ql_grip_paused_on');
					$.ajax({
						type: "POST",
						url: "tapi",
						data: {mode:'queue', name:'pause', value: pid, apikey: $.plush.apikey}
					});
				} else {
					$(this).toggleClass('sprite_ql_grip_queued_on').toggleClass('sprite_ql_grip_paused_on');
					$.ajax({
						type: "POST",
						url: "tapi",
						data: {mode:'queue', name:'resume', value: pid, apikey: $.plush.apikey}
					});
				}
			});
			
			// NZB individual deletion
			$('#queue .sprite_ql_cross').live('click', function(event) {
				if (!$.plush.confirmDeleteQueue || confirm($.plush.Tconfirmation)){
					delid = $(event.target).parent().parent().attr('id');
					$('#'+delid).fadeTo('normal',0.25);
					$.plush.pendingQueueRefresh = true;
					$.ajax({
						type: "POST",
						url: "tapi",
						data: {mode:'queue', name:'delete', value: delid, apikey: $.plush.apikey},
						success: function(){
							if ( $("#queueTable tr:visible").length - 1 < 1 ) { // don't leave stranded on non-page
								$.plush.skipRefresh = false;
								$.plush.queueforcerepagination = true;
								$.plush.RefreshQueue($.plush.queuecurpage-1);
							}
						}
					});
				}
			});

			// NZB change priority
			$('#queueTable .options .proc_priority').live('change',function(){
				var nzbid = $(this).parent().parent().attr('id');
				var oldPos = $('#'+nzbid)[0].rowIndex + $.plush.queuecurpage * $.plush.queuePerPage;
				$.ajax({
					type: "POST",
					url: "tapi",
					data: {mode:'queue', name:'priority', value: nzbid, value2: $(this).val(), apikey: $.plush.apikey},
					success: function(newPos){
						// reposition the nzb if necessary (new position is returned by the API)
						if (parseInt(newPos) < $.plush.queuecurpage * $.plush.queuePerPage
						 		|| ($.plush.queuecurpage + 1) * $.plush.queuePerPage < parseInt(newPos)) {
							$.plush.skipRefresh = false;
							$.plush.RefreshQueue();
						} else if (oldPos < newPos)
							$('#'+nzbid).insertAfter($('#queueTable tr:eq('+ (newPos - $.plush.queuecurpage * $.plush.queuePerPage) +')'));
						else if (oldPos > newPos)
							$('#'+nzbid).insertBefore($('#queueTable tr:eq('+ (newPos - $.plush.queuecurpage * $.plush.queuePerPage) +')'));
					}
				});
			});
			
			// 3-in-1 change nzb [category + processing + script]
			$('#queueTable .options .change_cat, #queueTable .options .change_opts, #queueTable .options .change_script').live('change',function(e){
				var val = $(this).parent().parent().attr('id');
				var cval = $(this).attr('class').split(" ")[0]; // ignore added "hovering" class
				$.ajax({
					type: "POST",
					url: "tapi",
					data: {mode: cval, value: val, value2: $(this).val(), apikey: $.plush.apikey},
					success: function(resp){
						// each category can define different priority/processing/script -- must be accounted for
						if (cval=="change_cat") {
							$.plush.skipRefresh = false;
							$.plush.RefreshQueue(); // this is not ideal, but the API does not yet offer a nice way of refreshing just one nzb
						}
					}
				});
			});
			
			// NZB icon hover states -- done here rather than in CSS:hover due to sprites
			$('#queueTable tr').live('mouseover mouseout', function(event) {
				if (event.type == 'mouseover') {
					$(this).find('td .icon_nzb_remove').addClass('sprite_ql_cross');
					$(this).find('td .sprite_ql_grip_queued').toggleClass('sprite_ql_grip_queued').toggleClass('sprite_ql_grip_queued_on');
					$(this).find('td .sprite_ql_grip_paused').toggleClass('sprite_ql_grip_paused').toggleClass('sprite_ql_grip_paused_on');
				} else {
					$(this).find('td .icon_nzb_remove').removeClass('sprite_ql_cross');
					$(this).find('td .sprite_ql_grip_queued_on').toggleClass('sprite_ql_grip_queued').toggleClass('sprite_ql_grip_queued_on');
					$(this).find('td .sprite_ql_grip_paused_on').toggleClass('sprite_ql_grip_paused').toggleClass('sprite_ql_grip_paused_on');
				}
			});
			$('#queueTable tr td .icon_nzb_remove').live('mouseover mouseout', function(event) {
				if (event.type == 'mouseover') {
					$(this).addClass('sprite_ql_cross_on');
				} else {
					$(this).removeClass('sprite_ql_cross_on');
				}
			});

			// Styling that is broken in IE (IE8 auto-closes select menus if defined)
			if (!$.browser.msie) {
				$('#queueTable tr').live('mouseover mouseout', function(event) {
					if (event.type == 'mouseover') {
						$(this).find('td.options select').addClass('hovering');
					} else {
						$(this).find('td.options select').removeClass('hovering');
					}
				});
			}
			
			// Sustained binding of events for elements added to DOM
			// Same idea as jQuery live(), but use jQuery livequery() plugin for functions/events not supported by live()
			$('#queueTable').livequery(function() {
				
				// Build pagination only when needed
				if ( ( $.plush.queueforcerepagination && $.plush.queuenoofslots > $.plush.queuePerPage) || $.plush.queuenoofslots > $.plush.queuePerPage && 
						Math.ceil($.plush.queueprevslots/$.plush.queuePerPage) != 
						Math.ceil($.plush.queuenoofslots/$.plush.queuePerPage) ) {
					
					$.plush.queueforcerepagination = false;
					if ( $("#queueTable tr:visible").length - 1 < 1 ) // don't leave stranded on non-page
						$.plush.queuecurpage--;
					$("#queue-pagination").pagination( $.plush.queuenoofslots , {
						current_page: $.plush.queuecurpage,
						items_per_page: $.plush.queuePerPage,
						num_display_entries: 8,
						num_edge_entries: 1,
						prev_text: "&laquo; "+$.plush.Tprev, // translation
						next_text: $.plush.Tnext+" &raquo;", // translation
						callback: $.plush.RefreshQueue
					});
					$('#queue-pagination span').removeClass('loading'); // hide spinner graphic
				} else if ($.plush.queuenoofslots <= $.plush.queuePerPage) {
					$("#queue-pagination").html(''); // remove pages if history empty
				}
				$.plush.queueprevslots = $.plush.queuenoofslots; // for the next refresh
				
				// Drag and drop sorting
				$("#queueTable").tableDnD({
					onDrop: function(table, row) {
						if (table.tBodies[0].rows.length < 2)
							return false;
						// determine which position the repositioned row is at now
						var val2;
						for ( var i=0; i < table.tBodies[0].rows.length; i++ ) {
							if (table.tBodies[0].rows[i].id == row.id) {
								val2 = (i + $.plush.queuecurpage * $.plush.queuePerPage);
								$.ajax({
									type: "POST",
									url: "tapi",
									data: {mode:'switch', value: row.id, value2: val2, apikey: $.plush.apikey},
									success: function(result){
										// change priority of the nzb if necessary (priority is returned by API)
										var newPriority = result.split(' ');
										newPriority = parseInt(newPriority[1]);
										if (newPriority != $('#'+row.id+' .options .proc_priority').val())
											$('#'+row.id+' .options .proc_priority').val(newPriority); // must be int, not string
									}
								});
								return false;
							}
						}
					}
				});
				
			}); // end livequery

		}, // end $.plush.InitQueue()
		
		
		// ***************************************************************
		//	$.plush.InitHistory() -- History Events

		InitHistory : function() {
			
			// Search
			$('#historySearchForm').submit(function(){
				$.plush.histcurpage = 0;
				$.plush.RefreshHistory();
				return false;
			});
			
			// Purge
			$('#hist_purge').click(function(event) {
				if (confirm( $.plush.TconfirmPurgeH )) {
					$.ajax({
						type: "POST",
						url: "tapi",
						data: {mode:'history', name:'delete', value:'all', apikey: $.plush.apikey},
						success: $.plush.RefreshHistory
					});
				}
			});

			// refresh on mouseout after deletion
			$('#history').hover(	// $.mouseout was triggering too often
				function(){}, // over
				function(){	  // out
					if ($.plush.pendingHistoryRefresh) {
						$.plush.pendingHistoryRefresh = false;
						$.plush.RefreshHistory();
					}
				}
			);

			// colorbox event bindings - so history doesn't refresh when viewing modal (thereby breaking rel prev/next)
			$().bind('cbox_open', function(){ $.plush.modalOpen=true; });
			$().bind('cbox_closed', function(){ $.plush.modalOpen=false; });
			$().bind('cbox_complete', function(){
				$('#cboxLoadedContent input').hide(); // hide back button
				$('#cboxLoadedContent h3').append('<br/><br/>'); // add spacing to header
			});

			// Set history per-page preference
			$("#history-pagination-perpage").val($.plush.histPerPage);
			$.plush.histcurpage = 0; // default 1st page
			
			// Pagination per-page selection
			$("#history-pagination-perpage").change(function(event){
				$.plush.histcurpage = Math.floor($.plush.histcurpage * $.plush.histPerPage / $(event.target).val() );
				$.plush.histPerPage = $(event.target).val();
				$.cookie('histPerPage', $.plush.histPerPage, { expires: 365 });
				$.plush.histforcerepagination = true;
				if ($.plush.histPerPage=="1")
					$("#history-pagination").html(''); // pagination rebuild not triggered on blank history (disabled)
				$.plush.RefreshHistory();
			});
			
			// NZB individual removal
			$('#history .sprite_ql_cross').live('click', function(event) {
				if (!$.plush.confirmDeleteHistory || confirm($.plush.Tconfirmation)){
					delid = $(event.target).parent().parent().attr('id');
					$('#'+delid).fadeTo('normal',0.25);
					$.plush.pendingHistoryRefresh = true;
					$.ajax({
						type: "POST",
						url: "tapi",
						data: {mode:'history', name:'delete', value: delid, apikey: $.plush.apikey},
						success: function(){
							if ( $("#historyTable tr:visible").length - 1 < 1 ) { // don't leave stranded on non-page
								$.plush.histforcerepagination = true;
								$.plush.RefreshHistory($.plush.histcurpage-1);
							}
						}
					});
				}
			});
			
			// Remove NZB hover states -- done here rather than in CSS:hover due to sprites
			$('#historyTable tr').live('mouseover mouseout', function(event) {
				if (event.type == 'mouseover') {
					$(this).find('.icon_nzb_remove').addClass('sprite_ql_cross');
				} else {
					$(this).find('.icon_nzb_remove').removeClass('sprite_ql_cross');
				}
			});
			$('#historyTable tr td .icon_nzb_remove').live('mouseover mouseout', function(event) {
				if (event.type == 'mouseover') {
					$(this).addClass('sprite_ql_cross_on');
				} else {
					$(this).removeClass('sprite_ql_cross_on');
				}
			});

			// Sustained binding of events for elements added to DOM
			$('#historyTable').livequery(function() {
				
				// modal for viewing script logs
				$('#historyTable .modal').colorbox({ width:"80%", height:"80%", initialWidth:"80%", initialHeight:"80%", speed:0, opacity:0.7 });
				
				// Build pagination only when needed
				if ($.plush.histPerPage=="1") // disabled history
					$("#history-pagination").html(''); // remove pages if history empty
				else if ( ( $.plush.histforcerepagination && $.plush.histnoofslots > $.plush.histPerPage) || $.plush.histnoofslots > $.plush.histPerPage && 
						Math.ceil($.plush.histprevslots/$.plush.histPerPage) != 
						Math.ceil($.plush.histnoofslots/$.plush.histPerPage) ) {
					
					$.plush.histforcerepagination = false;
					if ( $("#historyTable tr:visible").length - 1 < 1 ) // don't leave stranded on non-page
						$.plush.histcurpage--;
					$("#history-pagination").pagination( $.plush.histnoofslots , {
						current_page: $.plush.histcurpage,
						items_per_page: $.plush.histPerPage,
						num_display_entries: 8,
						num_edge_entries: 1,
						prev_text: "&laquo; "+$.plush.Tprev, // translation
						next_text: $.plush.Tnext+" &raquo;", // translation
						callback: $.plush.RefreshHistory
					});
					$('#history-pagination span').removeClass('loading'); // hide spinner graphic
				} else if ($.plush.histnoofslots <= $.plush.histPerPage)
					$("#history-pagination").html(''); // remove pages if history empty
				$.plush.histprevslots = $.plush.histnoofslots; // for the next refresh

			}); // end livequery
			
		}, // end $.plush.InitHistory()


		// ***************************************************************
		//	$.plush.Refresh()

		Refresh : function(force) {
			
			clearTimeout($.plush.timeout);	// prevent back-to-back refreshes
			
			if (force || $.plush.refreshRate > 0) {
				$.plush.RefreshQueue();
				$.plush.RefreshHistory();
				$.plush.timeout = setTimeout("$.plush.Refresh()", $.plush.refreshRate*1000); // loop
			} else if (!$('#history_stats').html()) {
				// Initial load if refresh rate saved as "Disabled"
				$.plush.RefreshQueue();
				$.plush.RefreshHistory();
			}
		}, // end $.plush.Refresh()


		// ***************************************************************
		//	$.plush.RefreshQueue() -- fetch HTML data from queue.tmpl (AHAH)
		
		RefreshQueue : function(page) {
			
			// Skip refresh if cursor hovers queue, to prevent UI annoyance
			if ($.plush.blockRefresh && $.plush.skipRefresh)
				return $('#manual_refresh_wrapper').addClass('refresh_skipped');

			// no longer a need for a pending queue refresh (associated with nzb deletions)
			$.plush.pendingQueueRefresh = false;

			// Deal with pagination for start/limit
			if (typeof( page ) == 'undefined' || page == "ok\n" || page < 0 )
				page = $.plush.queuecurpage;
			else if (page != $.plush.queuecurpage)
				$.plush.queuecurpage = page;

			// Refresh state notification
			$('#manual_refresh_wrapper').removeClass('refresh_skipped').addClass('refreshing');
			
			// Fetch updated content from queue.tmpl
			$.ajax({
				type: "POST",
				url: "queue/",
				data: {start: ( page * $.plush.queuePerPage ), limit: $.plush.queuePerPage},
				success: function(result){
					$('#queue').html(result);								// Replace queue contents with queue.tmpl
					$('#queue-pagination span').removeClass('loading');		// Remove spinner graphic from pagination
					$('#manual_refresh_wrapper').removeClass('refreshing');	// Refresh state notification
				},
				error: function() {
					$('#manual_refresh_wrapper').addClass('refresh_skipped');	// Failed refresh notification
				}
			});
			
		}, // end $.plush.RefreshQueue()

		
		// ***************************************************************
		//	$.plush.RefreshHistory() -- fetch HTML data from history.tmpl (AHAH)

		RefreshHistory : function(page) {

			// Skip refreshing when modal is open, which destroys colorbox rel prev/next
			if ($.plush.modalOpen)
				return;
			
			// no longer a need for a pending history refresh (associated with nzb deletions)
			$.plush.pendingHistoryRefresh = false;
			
			// Deal with pagination for start/limit
			if (typeof( page ) == 'undefined')
				page = $.plush.histcurpage;
			else if (page != $.plush.histcurpage)
				$.plush.histcurpage = page;
			
			if ($('#historySearchBox').val() && $.plush.histPerPage == "1") // history disabled
				var data = {start: 0, limit: 0, search: $('#historySearchBox').val() };
			else if ($('#historySearchBox').val())
				var data = {start: ( page * $.plush.histPerPage ), limit: $.plush.histPerPage, search: $('#historySearchBox').val() };
			else
				var data = {start: ( page * $.plush.histPerPage ), limit: $.plush.histPerPage};
				
			$.ajax({
				type: "POST",
				url: "history/",
				data: data,
				success: function(result){
					$('#history').html(result);								// Replace history contents with history.tmpl
					$('#history-pagination span').removeClass('loading');	// Remove spinner graphic from pagination
				}
			});
			
		}, // end $.plush.RefreshHistory()
		

		// ***************************************************************
		//	$.plush.SetQueueStats(str) -- called from queue.tmpl
		SetQueueStats : function(str) {
			$('#queue_stats').html(str);
		},
		

		// ***************************************************************
		//	$.plush.SetQueueSpeedLimit(str) -- called from queue.tmpl
		SetQueueSpeedLimit : function(str) {
			if ($("#maxSpeed-option").val() != str && !$.plush.focusedOnSpeedChanger)
				$("#maxSpeed-option").val(str);
		},
		

		// ***************************************************************
		//	$.plush.SetQueueFinishAction(str) -- called from queue.tmpl
		SetQueueFinishAction : function(str) {
			if ($("#onQueueFinish-option").val() != str)
				$("#onQueueFinish-option").val(str);
		},
		

		// ***************************************************************
		//	$.plush.SetQueuePauseInfo(paused,str) -- called from queue.tmpl
		SetQueuePauseInfo : function(paused,str) {
			$.plush.paused = paused;
					
			// Pause/resume button state
			if ( paused && !$('#pause_resume').hasClass('sprite_q_pause_on') )
				$('#pause_resume').removeClass('sprite_q_pause').addClass('sprite_q_pause_on');
			else if ( !paused && !$('#pause_resume').hasClass('sprite_q_pause') )
				$('#pause_resume').removeClass('sprite_q_pause_on').addClass('sprite_q_pause');

			// Pause interval
			(str == "0") ? $('#pause_int').html("") : $('#pause_int').html(str);
		},
		

		// ***************************************************************
		//	$.plush.SetQueueETAStats(speed,kbpersec,timeleft,eta) -- called from queue.tmpl
		SetQueueETAStats : function(speed,kbpersec,timeleft,eta) {

			// ETA/speed stats at top of queue
			if ($.plush.queuenoofslots < 1)
				$('#stats_speed, #stats_eta').html('&mdash;');
			else if (kbpersec < 1 && $.plush.paused)
				$('#stats_speed, #stats_eta').html('&mdash;');
			else {
				$('#stats_speed').html(speed+"B/s");
				$('#stats_eta').html(timeleft);
			}
			$('#time-left').attr('title',eta);	// Tooltip on "time left"
		},
		

		// ***************************************************************
		//	$.plush.SetWarnings(have_warnings,last_warning) -- called from queue.tmpl
		SetWarnings : function(have_warnings,last_warning) {
			$('#have_warnings').html('('+have_warnings+')');		// Update warnings count/latest warning text in main menu
			$('#last_warning').attr('title',last_warning);
		},


		// ***************************************************************
		//	$.plush.SetHistoryStats(str) -- called from history.tmpl
		SetHistoryStats : function(str) {
			$('#history_stats').html(str);
		}

	}; // end $.plush object

});


jQuery(document).ready(function($){
	$.plush.Init();		// Initialize Plush UI
	$.plush.Refresh();	// Initiate Plush refresh cycle
});

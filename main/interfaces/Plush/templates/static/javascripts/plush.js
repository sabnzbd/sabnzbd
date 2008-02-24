
var refreshRate = 5; // default

// once the DOM is ready, run this
$(document).ready(function() {
	// refresh rate
	if (ReadCookie('PlushRefresh')) {
		refreshRate = ReadCookie('PlushRefresh');
	} else {
		SetCookie('PlushRefresh',refreshRate);	
	}
	$('#refreshRateDisplay').html(refreshRate);

	// Queue & History layout restoration
	if ('sidebyside' == ReadCookie('PlushLayout')) {
		$("#queue").addClass("queue_sidebyside");
		$("#history").addClass("history_sidebyside");
	}

	// Queue & History layout togglers
	$('#layout_sidebyside').bind('click', function() { 
		$("#queue").addClass("queue_sidebyside");
		$("#history").addClass("history_sidebyside");
		SetCookie('PlushLayout','sidebyside');
	});
	$('#layout_toptobottom').bind('click', function() { 
		$("#queue").removeClass("queue_sidebyside");
		$("#history").removeClass("history_sidebyside");
		SetCookie('PlushLayout','toptobottom');
	});
	
	// Set up lightbox floating window
	$("a.greybox").click(function(){
		var t = this.title || this.innerHTML || this.href;
		GB_show(t,this.href,500,700);
		return false;
    });
	// Set up Main Menu actions
	$('#options').bind('click', function() { 
		$('#options').toggleClass('on');
		$('#optionsMenu').toggle();
	});
	$('#plusnzb').bind('click', function() { 
		$('#plusnzb').toggleClass('on');
		$('#nzbMenu').toggle();
	});
	// Set up options refresh rate slider	
	$('.refreshSlider').Slider({
		accept : '.refreshIndicator',
		fractions : 100,
		onSlide : function(cordx, cordy, x , y) {
			if (!cordx || cordx==0)
				cordx = 1;
			$('#refreshRateDisplay').html(cordx);
			refreshRate = cordx;
			SetCookie('PlushRefresh',refreshRate);
		}
	});
	// Set up +NZB
	$('#addNZBbyID').bind('click', function() { 
		$.ajax({
			type: "GET",
			url: "addID",
			data: "id="+$("#addID").val()+"&pp="+$("#addID_pp").val(),
			success: function(){
    			RefreshTheQueue();
			}
		});
		$("#addID").val('by Newzbin ID/NB32');
	});
	$('#addNZBbyURL').bind('click', function() { 
		$.ajax({
			type: "GET",
			url: "addURL",
			data: "url="+$("#addURL").val()+"&pp="+$("#addURL_pp").val(),
			success: function(){
    			RefreshTheQueue();
			}
		});
		$("#addURL").val('by URL');
	});
	
	// toggle queue shutdown - from options menu
	if ($('#queue_shutdown_option')) {
		$('#queue_shutdown_option').bind('click', function() { 
			if(confirm('Are you sure you want to toggle shutting down your entire computer when the queue downloads have finished?')){
				$.ajax({
					type: "GET",
					url: "queue/tog_shutdown",
					success: function(){
		    			RefreshTheQueue();
					}
				});
			}
		});
	}
	
	
	// Set up Queue Menu actions
	$('#queue').click(function(event) {
		if ($(event.target).is('#pause_resume')) {
			if ($(event.target).attr('class') == 'active')
				$.ajax({
					type: "GET",
					url: "queue/resume",
					success: function(){
		    			RefreshTheQueue();
					}
				});
			else
				$.ajax({
					type: "GET",
					url: "queue/pause",
					success: function(result){
		    			RefreshTheQueue(result);
					}
				});
		}
		else if ($(event.target).is('#queue_verbosity')) {
			$.ajax({
				type: "GET",
				url: "queue/tog_verbose",
				success: function(){
	    			RefreshTheQueue();
				}
			});
		}
		else if ($(event.target).is('#queue_sortage')) {
			$.ajax({
				type: "GET",
				url: "queue/sort_by_avg_age",
				success: function(){
	    			RefreshTheQueue();
				}
			});
		}
		else if ($(event.target).is('#queue_shutdown')) {
			$.ajax({
				type: "GET",
				url: "queue/tog_shutdown",
				success: function(){
	    			RefreshTheQueue();
				}
			});
		}
		else if ($(event.target).is('.btnDelete')) {
			$.ajax({
				type: "GET",
				url: 'queue/delete?uid='+$(event.target).parent().parent().attr('id'),
				success: function(){
	    			RefreshTheQueue();
				}
			});
		}
	});
	
	
	// Set up History Menu actions
	$('#history').click(function(event) {
		if ($(event.target).is('#history_verbosity')) {
			$('#history').load('history/tog_verbose');
		}
		else if ($(event.target).is('#history_purge')) {
			$('#history').load('history/purge');
		}
	});
	
	// initiate refreshes
	MainLoop();
	
	
});

// calls itself after `refreshRate` seconds
function MainLoop() {
	
	// ajax calls
	RefreshTheQueue();
	$('#history').load('history');

	// loop
	setTimeout("MainLoop()",refreshRate*1000);
}

// in a function since some processes need to refresh the queue outside of MainLoop()
function RefreshTheQueue() {
	$('#queue').load('queue', function(){
		document.title = 'SAB+ '+$('#stats_kbpersec').html()+' KB/s '+$('#stats_eta').html()+' Left of '+$('#stats_noofslots').html();
		$("#queueTable").tableDnD({
	    	//onDragClass: "myDragClass",
	    	onDrop: function(table, row) {
            	var rows = table.tBodies[0].rows;
				var droppedon = "";
				
				if (rows.length < 2)
					return;
				
				if (rows[0].id == row.id)					// dragged to the top, replaced the first one
					droppedon = rows[1].id;
				else if (rows[rows.length-1].id == row.id)	// dragged to the bottom, replaced the last one
					droppedon = rows[rows.length-2].id;
				else										// search for where it was dropped on
            		for (var i=0; i<rows.length; i++)
						if (i>0 && rows[i-1].id == row.id)
							droppedon = rows[i].id;
				if (droppedon!="")
					ChangeOrder("switch?uid1="+row.id+"&uid2="+droppedon);
	    	}
		});
	});
}

// change post-processing options within queue
function ChangeProcessingOption (nzo_id,op) {
	$.ajax({
		type: "GET",
		url: 'queue/change_opts?nzo_id='+nzo_id+'&pp='+op,
	  	success: function(msg){
   			return RefreshTheQueue();
		}
	});
}

// change queue order
// switch?uid1=$slot.nzo_id&uid2=$slotinfo[i].nzo_id
function ChangeOrder (result) {
	$.ajax({
		type: "GET",
		url: "queue/"+result,
	  	success: function(msg){
   			return RefreshTheQueue();
		}
	});
}

// queue verbosity re-order arrows top/up/down/bottom
function ManipNZF (nzo_id, nzf_id, action) {
	if (action == 'Drop') {
		$.ajax({
			type: "GET",
			url: "queue/removeNzf",
			data: "nzo_id="+nzo_id+"&nzf_id="+nzf_id,
			success: function(){
   				return RefreshTheQueue();
			}
		});
	} else {	// moving top/up/down/bottom (delete is above)
		$.ajax({
			type: "GET",
			url: 'queue/'+nzo_id+'/bulk_operation',
			data: nzf_id + '=on' + '&' + 'action_key=' + action,
			success: function(){
   				return RefreshTheQueue();
			}
		});
	}
}

// ajax file upload
function startCallback() {
    // make something useful before submit (onStart)
    return true;
}

function completeCallback(response) {
    // make something useful after (onComplete)
	RefreshTheQueue();
	return true;
}


// used to store layout settings
function SetCookie(name,val) {
	var date = new Date();
	date.setTime(date.getTime()+(365*24*60*60*1000));
	document.cookie = name+"="+val+"; expires="+ date.toGMTString() +"; path=/";
}

// used during initialization to restore layout settings
function ReadCookie(name) {
	var nameEQ = name + "=";
	var ca = document.cookie.split(';');
	for(var i=0;i < ca.length;i++) {
		var c = ca[i];
		while (c.charAt(0)==' ') c = c.substring(1,c.length);
		if (c.indexOf(nameEQ) == 0) return c.substring(nameEQ.length,c.length);
	}
	return null;
}

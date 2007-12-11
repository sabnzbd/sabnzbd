/*
	plush.js
	SABnzbd+ Plush
	By: Nathan Langlois
   *********************/

var refreshRate = 4; // default

// once the DOM is ready, run this
$(document).ready(function() {
	// refresh rate
	if (ReadCookie('PlushRefresh')) {
		refreshRate = ReadCookie('PlushRefresh');
		$('#refreshRateDisplay').html(refreshRate);
		SetCookie('PlushRefresh',refreshRate);
	} else {
		SetCookie('PlushRefresh',4);	
	}
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
    			$('#queue').load('queue', function(){
					document.title = 'SAB+ '+$('#stats_kbpersec').html()+$('#stats_noofslots').html()+' Queued';
				});
			}
		});
		$("#addID").val('by Report ID');
	});
	$('#addNZBbyURL').bind('click', function() { 
		$.ajax({
			type: "GET",
			url: "addURL",
			data: "url="+$("#addURL").val()+"&pp="+$("#addURL_pp").val(),
			success: function(){
    			$('#queue').load('queue', function(){
					document.title = 'SAB+ '+$('#stats_kbpersec').html()+$('#stats_noofslots').html()+' Queued';
				});
			}
		});
		$("#addURL").val('by URL');
	});
	$('#addNZBbyFile').bind('click', function() { 
		$("form").submit();
	});
	
	
	// Set up Queue Menu actions
	$('#queue').click(function(event) {
		if ($(event.target).is('#pause_resume')) {
			if ($(event.target).attr('class') == 'active')
				$('#queue').load('queue/resume');
			else
				$('#queue').load('queue/pause');
		}
		else if ($(event.target).is('#queue_verbosity')) {
			$('#queue').load('queue/tog_verbose');
		}
		else if ($(event.target).is('#queue_sortage')) {
			$('#queue').load('queue/sort_by_avg_age');
		}
		else if ($(event.target).is('#queue_shutdown')) {
			$('#queue').load('queue/tog_shutdown');
		}
		else if ($(event.target).is('.btnDelete')) {
			$('#queue').load('queue/delete?uid='+$(event.target).parent().parent().attr('id'));
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
	
	
	MainLoop();
	
	
});

function MainLoop() {
	
	// ajax calls
	$('#queue').load('queue', function(){
		document.title = 'SAB+ '+$('#stats_kbpersec').html()+$('#stats_noofslots').html()+' Queued';
	});
	$('#history').load('history');

	// loop
	setTimeout("MainLoop()",refreshRate*1000);
}

// change post-processing options within queue
function ChangeProcessingOption (id,op) {
	$('#queue').load('queue/change_opts?nzo_id='+id+'&pp='+op);
}

// change queue order
function ChangeOrder (result) {
	$('#queue').load('queue/'+result);
}

// queue verbosity re-order arrows top/up/down/bottom
function ManipNZF (nzo_id, nzf_id, action) {
	if (action == 'Drop') {
		$.ajax({
			type: "GET",
			url: "queue/removeNzf",
			data: "nzo_id="+nzo_id+"&nzf_id="+nzf_id,
			success: function(){
    			$('#queue').load('queue', function(){
					document.title = 'SAB+ '+$('#stats_kbpersec').html()+$('#stats_noofslots').html()+' Queued';
				});
			}
		});
	} else {
		$.ajax({
			type: "GET",
			url: 'queue/'+nzo_id+'/bulk_operation',
			data: nzf_id + '=on' + '&' + 'action_key=' + action,
			success: function(){
    			$('#queue').load('queue', function(){
					document.title = 'SAB+ '+$('#stats_kbpersec').html()+$('#stats_noofslots').html()+' Queued';
				});
			}
		});
	}
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


















/* Greybox Redux
 * Required: http://jquery.com/
 * Written by: John Resig
 * Based on code by: 4mir Salihefendic (http://amix.dk)
 * License: LGPL (read more in LGPL.txt)
 */
var GB_DONE = false;
function GB_show(caption, url, height, width) {
  GB_HEIGHT = 600;
  GB_WIDTH = 820;
  if(!GB_DONE) {
    $(document.body)
      .append("<div id='GB_overlay'></div><div id='GB_window'><div id='GB_caption'></div>"
        + "<img src='static/images/gb_close.gif' alt='Close window'/></div>");
    $("#GB_window img").click(GB_hide);
    $("#GB_overlay").click(GB_hide);
    $(window).resize(GB_position);
    GB_DONE = true;
  }
  $("#GB_frame").remove();
  $("#GB_window").append("<iframe id='GB_frame' src='"+url+"'></iframe>");
  $("#GB_caption").html(caption);
  $("#GB_overlay").show();
  GB_position();
  //if(GB_ANIMATION)
  //  $("#GB_window").slideDown("slow");
  //else
  $("#GB_window").show();
}

function GB_hide() {
  $("#GB_window,#GB_overlay").hide();
}

function GB_position() {
  var de = document.documentElement;
  var w = self.innerWidth || (de&&de.clientWidth) || document.body.clientWidth;
  $("#GB_window").css({width:GB_WIDTH+"px",height:GB_HEIGHT+"px",
    left: ((w - GB_WIDTH)/2)+"px" });
  $("#GB_frame").css("height",GB_HEIGHT - 32 +"px");
}

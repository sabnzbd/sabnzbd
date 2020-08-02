// ***************************************************************
// Plush main code as follows, by pairofdimes (see LICENSE-CC.txt)

jQuery(function($){

  $.plush = {

  // ***************************************************************
  //  Plush defaults

  refreshRate:          $.cookie('plushRefreshRate')     ? $.cookie('plushRefreshRate')  : 4, // refresh rate in seconds
  speedLimitType:       $.cookie('plushSpeedLimitType')  ? $.cookie('plushSpeedLimitType')  : '%', // how to display the speedlimit
  containerWidth:       $.cookie('plushContainerWidth')  ? $.cookie('plushContainerWidth')  : '100%', // width of all elements on page
  queuePerPage:         $.cookie('plushQueuePerPage')    ? $.cookie('plushQueuePerPage') : 5, // pagination - nzbs per page
  histPerPage:          $.cookie('plushHistPerPage')     ? $.cookie('plushHistPerPage')  : 5, // pagination - nzbs per page
  confirmDeleteQueue:   $.cookie('plushConfirmDeleteQueue') == 0 ? false : true,  // confirm queue nzb removal
  confirmDeleteHistory: $.cookie('plushConfirmDeleteHistory') == 0 ? false : true, // confirm history nzb removal
  blockRefresh:         $.cookie('plushBlockRefresh') == 0 ? false : true, // prevent refreshing when hovering queue
  failedOnly:           $.cookie('plushFailedOnly') == 1 ? 1 : 0, // prevent refreshing when hovering queue
  multiOps:             $.cookie('plushMultiOps') == 0 ? false : true, // is multi-operations menu visible in queue
  noTopMenu:            $.cookie('plushNoTopMenu') == 1 ? false : true, // is top menu visible
  multiOpsChecks:       null,

  // ***************************************************************
  //  $.plush.Init() -- initialize all the UI events

  Init : function() {
    $.plush.InitAddNZB();
    $.plush.InitMainMenu();
    $.plush.InitQueue();
    $.plush.InitHistory();
    $.plush.InitTooltips();
  }, // end $.plush.Init()


  // ***************************************************************
  //  $.plush.InitAddNZB() -- "Add NZB" Methods

  InitAddNZB : function() {
    // Fetch NZB by URL/Newzbin Report ID
    $('#addID').click(function(){ // also works when hitting enter because of <form>
      if ($('#addID_input').val()!='URL') {
        $.ajax({
          headers: {"Cache-Control": "no-cache"},
          type: "POST",
          url: "api",
          data: {
            mode:     'addurl',
            name:     $("#addID_input").val(),
            pp:       $("#addID_pp").val(),
            script:   $("#addID_script").val(),
            cat:      $("#addID_cat").val(),
            priority: $("#addID_priority").val(),
            nzbname:  $("#addID_nzbname").val(),
            apikey:   $.plush.apikey
          },
          success: $.plush.RefreshQueue
        });
        $("#addID_input").val('');
        $('#nzbname').val('');
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
  $('#uploadNZBForm').submit( function(){
    $('#uploadingSpinner').fadeIn('slow');
    return AIM.submit(this, {'onComplete': function(){ $('#uploadingSpinner').fadeOut('slow'); $('#uploadNZBFile,#nzbname').val(''); $.plush.RefreshQueue(); }})
  });

  // Fetch Newzbin Bookmarks
  /*$('#fetch_newzbin_bookmarks').click(function(){
    $.ajax({
      type: "POST",
      url: "api",
      data: {mode:'newzbin', name:'get_bookmarks', apikey: $.plush.apikey},
      success: function(result){
        $.plush.RefreshQueue();
      }
    });
  });*/

  }, // end $.plush.InitAddNZB()


  // ***************************************************************
  //  $.plush.InitMainMenu() -- Main Menu Events

  InitMainMenu : function() {

  $('.juiButton').button();

  // Main menu -- uses jQuery hoverIntent
  $("#main_menu ul.sf-menu").superfish({
    autoArrows: true,
      dropShadows: false,
    speed:0, delay:800
  });
  $(".queue-buttons ul").superfish({
    autoArrows: false,
    dropShadows: false,
  speed:0, delay:800
  });
  $('.sprite_q_menu_pausefor').hover(
    function(){ $(this).addClass('sprite_q_menu_pauseforsfHover'); },
    function(){ $(this).removeClass('sprite_q_menu_pauseforsfHover'); }
  );
  $('.sprite_q_queue').hover(
    function(){ $(this).addClass('sprite_q_queuesfHover'); },
    function(){ $(this).removeClass('sprite_q_queuesfHover'); }
  );

  // fix for touch devices -- toggle visibility
  $('.sprite_q_menu_pausefor').bind('touchend', function(e) {
      if (! $.browser.safari) {
        e.preventDefault();
        if( $(this).hasClass('sprite_q_menu_pauseforsfHover') ) {
          $(this).find("ul").toggle();
        }
      }
  });
  $('.sprite_q_queue').bind('touchend', function(e) {
      if (! $.browser.safari) {
        e.preventDefault();
        if( $(this).hasClass('sprite_q_queuesfHover') ) {
          $(this).find("ul").toggle();
        }
      }
  });

  // modals
  $("#help").colorbox({ inline:true, href:"#help_modal", title:$("#help").text(),
    innerWidth:"375px", innerHeight:"350px", initialWidth:"375px", initialHeight:"350px", speed:0, opacity:0.7
  });
  $("#add_nzb").colorbox({ inline:true, href:"#add_nzb_modal", title:$("#add_nzb").text(),
    innerWidth:"375px", innerHeight:"370px", initialWidth:"375px", initialHeight:"370px", speed:0, opacity:0.7
  });
  $("#plush_options").colorbox({ inline:true, href:"#plush_options_modal", title:$("#plush_options").text(),
    innerWidth:"375px", innerHeight:"350px", initialWidth:"375px", initialHeight:"350px", speed:0, opacity:0.7
  });

  // Save the type of speedlimit display
  $('#maxSpeed-label').change(function() {
    $.plush.speedLimitType = $(this).val();
    $.cookie('plushSpeedLimitType', $.plush.speedLimitType, { expires: 365 });
    // Update the text
    $.plush.focusedOnSpeedChanger = false;
    $.plush.SetQueueSpeedLimit();
  })
  // Set stored value
  $('#maxSpeed-label').val($.plush.speedLimitType)

  // Max Speed main menu input -- don't change value on refresh when focused
  $("#maxSpeed-option").focus(function(){
    $.plush.focusedOnSpeedChanger = true;
  }).blur(function(){
    $.plush.focusedOnSpeedChanger = false;
  }).keyup(function (e) {
    // Catch the enter
    if (e.keyCode == 13) {
      $("#maxSpeed-enable").click()
    }
  })

  // Submit the new speedlimit
  $("#maxSpeed-enable, #maxSpeed-disable").click( function(e) {
    // Remove
    if ($(e.target).attr('id')=="maxSpeed-disable") {
        $('#maxSpeed-option').val('');
    }
    var speedLimit = $('#maxSpeed-option').val();
    if (speedLimit && speedLimit!="") {
        $('#speed-wrapper .sprite_q_menu_pausefor').addClass('sprite_q_menu_pausefor_on');
    } else {
        $('#speed-wrapper .sprite_q_menu_pausefor').removeClass('sprite_q_menu_pausefor_on');
    }
    // Transform if nessecary
    if(speedLimit != '' && $.plush.speedLimitType != '%') {
        // Add the label
        speedLimit = speedLimit + $.plush.speedLimitType;
    }
    $.ajax({
      headers: {"Cache-Control": "no-cache"},
      type: "POST",
      url: "api",
      data: {mode:'config', name:'set_speedlimit', value: speedLimit, apikey: $.plush.apikey}
    });
    // Update
    $.plush.RefreshQueue();
  });

  // Refresh rate
  $("#refreshRate-option").val($.plush.refreshRate).change( function() {
    $.plush.refreshRate = $("#refreshRate-option").val();
    $.cookie('plushRefreshRate', $.plush.refreshRate, { expires: 365 });
    $.plush.Refresh();
  });

  // Container width
  $("#containerWidth-option").val($.plush.containerWidth).change( function() {
    $.plush.containerWidth = $("#containerWidth-option").val();
    $.cookie('plushContainerWidth', $.plush.containerWidth, { expires: 365 });
    $('#master-width').css('width',$.plush.containerWidth);
  }).trigger('change');

  // Confirm Queue Deletions toggle
  $("#confirmDeleteQueue").prop('checked', $.plush.confirmDeleteQueue ).change( function() {
    $.plush.confirmDeleteQueue = $("#confirmDeleteQueue").prop('checked');
    $.cookie('plushConfirmDeleteQueue', $.plush.confirmDeleteQueue ? 1 : 0, { expires: 365 });
  });

  // Confirm History Deletions toggle
  $("#confirmDeleteHistory").prop('checked', $.plush.confirmDeleteHistory ).change( function() {
    $.plush.confirmDeleteHistory = $("#confirmDeleteHistory").prop('checked');
    $.cookie('plushConfirmDeleteHistory', $.plush.confirmDeleteHistory ? 1 : 0, { expires: 365 });
  });

  // Block Refreshes on Hover toggle
  $("#blockRefresh").prop('checked', $.plush.blockRefresh ).change( function() {
    $.plush.blockRefresh = $("#blockRefresh").prop('checked');
    $.cookie('plushBlockRefresh', $.plush.blockRefresh ? 1 : 0, { expires: 365 });
  });

  // Sabnzbd restart
  $('#sabnzbd_restart').click( function(){
    return confirm($(this).attr('rel'));
  });

  // Sabnzbd shutdown
  $('#sabnzbd_shutdown').click( function(){
    return confirm($(this).attr('rel'));
  });

  // Queue "Upon Completion" script
  $("#onQueueFinish-option").change( function() {
    if ($(this).val() && $(this).val()!="")
      $('.sprite_q_queue').addClass('sprite_q_queue_on');
    else
      $('.sprite_q_queue').removeClass('sprite_q_queue_on');
    $.ajax({
      headers: {"Cache-Control": "no-cache"},
      type: "POST",
      url: "api",
      data: {mode:'queue', name:'change_complete_action', value: $(this).val(), apikey: $.plush.apikey}
    });
  });

  // Queue Purge
  $('#queue_purge').click(function(event) {
    $.colorbox({ inline:true, href:"#queue_purge_modal", title:'',
      innerWidth:"375px", innerHeight:"250px", initialWidth:"375px", initialHeight:"250px", speed:0, opacity:0.7
    });
    return false;
  });
  $('#queue_purge_modal input:submit').click(function(){
    var value = $(this).attr('name');
    var del_files=0
    if (value=="delete") {
      del_files=1;
      value="all";
    }
    $.ajax({
      headers: {"Cache-Control": "no-cache"},
      type: "POST",
      url: "api",
      data: {mode:'queue', name:'delete', value:value, del_files:del_files, search: $('#queueSearchBox').val(), apikey: $.plush.apikey},
      success: function(){
        $.colorbox.close();
        $.plush.modalOpen=false;
        $.plush.RefreshQueue();
      }
    });
  });

  // Retry all failed jobs
  $('#queue_retry').click(function(event) {
    $.colorbox({ inline:true, href:"#queue_retry_modal", title:'',
      innerWidth:"375px", innerHeight:"250px", initialWidth:"375px", initialHeight:"250px", speed:0, opacity:0.7
    });
    return false;
  });
  $('#queue_retry_modal input:submit').click(function(){
    $.ajax({
      headers: {"Cache-Control": "no-cache"},
      type: "POST",
      url: "api",
      data: {mode:'retry_all', apikey: $.plush.apikey},
      success: function(){
        $.colorbox.close();
        $.plush.modalOpen=false;
        $.plush.RefreshQueue();
      }
    });
  });


  // Queue sort (6-in-1)
  $('#queue_sort_list .queue_sort').click(function(event) {
    var sort, dir;
    switch ($(this).attr('id')) {
      case 'sortAgeAsc':    sort='avg_age'; dir='asc';  break;
      case 'sortAgeDesc':   sort='avg_age'; dir='desc'; break;
      case 'sortNameAsc':   sort='name';    dir='asc';  break;
      case 'sortNameDesc':  sort='name';    dir='desc'; break;
      case 'sortSizeAsc':   sort='size';    dir='asc';  break;
      case 'sortSizeDesc':  sort='size';    dir='desc'; break;
    }
    $.ajax({
      headers: {"Cache-Control": "no-cache"},
      type: "POST",
      url: "api",
      data: {mode:'queue', name:'sort', sort: sort, dir: dir, apikey: $.plush.apikey},
      success: $.plush.RefreshQueue
    });
  });

  // Queue pause intervals
  $('#set_pause_list .set_pause').click(function(event) {
    var minutes = $(event.target).attr('rel');
    if (minutes == "custom")
      minutes = prompt($(event.target).attr('title'));
    $.plush.SetQueuePauseInfo(true,minutes+':00');
    $.ajax({
      headers: {"Cache-Control": "no-cache"},
      type: "POST",
      url: "api",
      data: {mode:'config', name:'set_pause', value: minutes, apikey: $.plush.apikey},
      success: $.plush.RefreshQueue
    });
  });

  // Get Bookmarks
  $('#get_bookmarks_now').click(function() {
    $.ajax({
      headers: {"Cache-Control": "no-cache"},
      type: "POST",
      url: "api",
      data: {mode:'newzbin', name:'get_bookmarks', apikey: $.plush.apikey},
      success: $.plush.RefreshQueue
    });
  });

  // Reset Quota
  $('#reset_quota_now').click(function() {
    $.ajax({
      headers: {"Cache-Control": "no-cache"},
      type: "POST",
      url: "api",
      data: {mode:'reset_quota', apikey: $.plush.apikey},
      success: $.plush.RefreshQueue
    });
  });

  // Get RSS
  $('#get_rss_now').click(function() {
    $.ajax({
      headers: {"Cache-Control": "no-cache"},
      type: "POST",
      url: "api",
      data: {mode:'rss_now', apikey: $.plush.apikey},
      success: $.plush.RefreshQueue
    });
  });

  // Get Watched folder
  $('#get_watched_now').click(function() {
    $.ajax({
      headers: {"Cache-Control": "no-cache"},
      type: "POST",
      url: "api",
      data: {mode:'watched_now', apikey: $.plush.apikey},
      success: $.plush.RefreshQueue
    });
  });

  // Resume Post Processing
  $('#resume_pp').click(function() {
    $.ajax({
      headers: {"Cache-Control": "no-cache"},
      type: "POST",
      url: "api",
      data: {mode:'resume_pp', apikey: $.plush.apikey},
      success: $.plush.RefreshQueue
    });
  });

  $('#multiops_toggle').click(function(){
    if( $('#multiops_bar').is(':visible') ) { // hide
      $('#multiops_bar').hide();
      $.plush.multiOps = false;
      $.plush.multiOpsChecks = null;
      $('#queue tr td.nzb_status_col input').remove();
    } else { // show
      $('#multiops_bar').show();
      $.plush.multiOps = true;
      $.plush.multiOpsChecks = new Array();
      $('<input type="checkbox" class="multiops" />').appendTo('#queue tr td.nzb_status_col');
    }
    $.cookie('plushMultiOps', $.plush.multiOps ? 1 : 0, { expires: 365 });
  });
  if ($.plush.multiOps)
    $('#multiops_toggle').trigger('click');

  $('#topmenu_toggle').click(function(){
    if( $('#topmenu_bar').is(':visible') ) { // hide
      $('#topmenu_bar').hide();
      $.plush.noTopMenu = true;
    } else { // show
      $('#topmenu_bar').show();
      $.plush.noTopMenu = false;
    }
    $.cookie('plushNoTopMenu', $.plush.noTopMenu ? 1 : 0, { expires: 365 });
  });
  if ($.plush.noTopMenu)
    $('#topmenu_toggle').trigger('click');

  // Manual refresh
  $('#manual_refresh_wrapper').click(function(e){
    // prevent button text highlighting
    e.target.onselectstart = function() { return false; };
    e.target.unselectable = "on";
    e.target.style.MozUserSelect = "none";
    //e.target.style.cursor = "default";

  $.plush.Refresh(true);
  return false;
});

  }, // end $.plush.InitMainMenu()


  // ***************************************************************
  //  $.plush.InitTooltips() -- title tootlips on hover

  InitTooltips : function() {
    // TO DO:
    //    clean up implementation, unfortunately was not built as a plugin
    //    fix glitching on superfish tooltips (#uploadTip doesn't work, #fetch_newzbin_bookmarks only works when hover from side)

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
    delay: 0,     // changed
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

  // static-element tooltips
  $('body').delegate('#pausefor_title, #time-left, #multi_delete, #explain-blockRefresh, #pause_resume, #hist_purge, #queueTable td.download-title a, #queueTable td.eta span, #queueTable td.options .icon_nzb_remove, #historyTable td.options .icon_nzb_remove, #historyTable td div.icon_history_verbose', 'mouseover mouseout mousemove', function(event) {
    var link = this,
      $link = $(this);

  if (event.type == 'mouseover') {
    tip.title = link.title;
    link.title = '';

  showTip = setTimeout(function() {

  $link.data('tipActive', true);

  tip.position(event);

  $liveTip
  .html('<div>' + tip.title + '</div>') //<div>' + link.href + '</div>')    // changed
  //.fadeOut(0)                               // changed
  .show();//.fadeIn(200);                           // changed

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
  //  $.plush.InitQueue() - Queue Events

  InitQueue : function() {

  // Search
  $('#queueSearchForm').submit(function(){
    $.plush.queuecurpage = 0; // default 1st page
    $.plush.RefreshQueue();
    return false;
  });

  // Pause/resume toggle (queue)
  $('#pause_resume').click(function(event) {
    $('.queue-buttons-pause .sprite_q_menu_pausefor').removeClass('sprite_q_menu_pausefor_on');
    if ( $(event.target).hasClass('sprite_q_pause_on') ) {
      $('#pause_resume').removeClass('sprite_q_pause_on').addClass('sprite_q_pause');
      $('#pause_int').html("");
      $.ajax({
        headers: {"Cache-Control": "no-cache"},
        type: "POST",
        url: "api",
        data: {mode:'resume', apikey: $.plush.apikey}
      });
    } else {
      $('#pause_resume').removeClass('sprite_q_pause').addClass('sprite_q_pause_on');
      $('#pause_int').html("");
      $.ajax({
        headers: {"Cache-Control": "no-cache"},
        type: "POST",
        url: "api",
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
    $.cookie('plushQueuePerPage', $.plush.queuePerPage, { expires: 365 });
    $.plush.queueforcerepagination = true;
    $.plush.RefreshQueue();
  });

  // Skip queue refresh on mouseover
  $('#queue').hover(
    function(){ $.plush.skipRefresh=true; }, // over
    function(){ $.plush.skipRefresh=false; } // out
  );

  // NZB pause/resume individual toggle
  $('#queue').delegate('.nzb_status','click',function(event){
    var pid = $(this).parent().parent().attr('id');
    if ($(this).hasClass('sprite_ql_grip_resume_on')) {
      $(this).toggleClass('sprite_ql_grip_resume_on').toggleClass('sprite_ql_grip_pause_on');
      $.ajax({
        headers: {"Cache-Control": "no-cache"},
        type: "POST",
        url: "api",
        data: {mode:'queue', name:'pause', value: pid, apikey: $.plush.apikey}
      });
    } else {
      $(this).toggleClass('sprite_ql_grip_resume_on').toggleClass('sprite_ql_grip_pause_on');
      $.ajax({
        headers: {"Cache-Control": "no-cache"},
        type: "POST",
        url: "api",
        data: {mode:'queue', name:'resume', value: pid, apikey: $.plush.apikey}
      });
    }
  });

  // NZB individual deletion
  $('#queue').delegate('.sprite_ql_cross','click', function(event) {
    $('#delete_nzb_modal_title').text( $(this).parent().prev().prev().prev().children('a:first').text() );
    $('#delete_nzb_modal_job').val( $(this).parent().parent().attr('id') );
    $('#delete_nzb_modal_remove_files').button('enable');
    $('#delete_nzb_modal_mode').val( 'queue' );
    $.colorbox({ inline:true, href:"#delete_nzb_modal", title:$(this).text(),
      innerWidth:"600px", innerHeight:"150px", initialWidth:"600px", initialHeight:"150px", speed:0, opacity:0.7
    });
    return false;
  });


//        if (!$.plush.confirmDeleteQueue || confirm($.plush.Tconfirmation)){
/*          delid = $(event.target).parent().parent().attr('id');
  $('#'+delid).fadeTo('normal',0.25);
  $.plush.pendingQueueRefresh = true;
  $.ajax({
    type: "POST",
    url: "api",
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
*/

  // NZB change priority
  $('#queue .proc_priority').live('change',function(){
    var nzbid = $(this).parent().parent().attr('id');
    var oldPos = $('#'+nzbid)[0].rowIndex + $.plush.queuecurpage * $.plush.queuePerPage;
    $.ajax({
      headers: {"Cache-Control": "no-cache"},
      type: "POST",
      url: "api",
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
  $('#queue .change_cat, #queue .change_opts, #queue .change_script').live('change',function(e){
    var val = $(this).parent().parent().attr('id');
    var cval = $(this).attr('class').split(" ")[0]; // ignore added "hovering" class
    $.ajax({
      headers: {"Cache-Control": "no-cache"},
      type: "POST",
      url: "api",
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
      $(this).find('td .sprite_ql_grip_resume').toggleClass('sprite_ql_grip_resume').toggleClass('sprite_ql_grip_resume_on');
      $(this).find('td .sprite_ql_grip_pause').toggleClass('sprite_ql_grip_pause').toggleClass('sprite_ql_grip_pause_on');
    } else {
      $(this).find('td .icon_nzb_remove').removeClass('sprite_ql_cross');
      $(this).find('td .sprite_ql_grip_resume_on').toggleClass('sprite_ql_grip_resume').toggleClass('sprite_ql_grip_resume_on');
      $(this).find('td .sprite_ql_grip_pause_on').toggleClass('sprite_ql_grip_pause').toggleClass('sprite_ql_grip_pause_on');
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
    num_display_entries: 4,
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

  // adjust odd row background coloring
  $("tr:odd", '#queueTable').removeClass("alt");
  $("tr:even", '#queueTable').addClass("alt");

  // determine which position the repositioned row is at now
  var val2;
  for ( var i=0; i < table.tBodies[0].rows.length; i++ ) {
    if (table.tBodies[0].rows[i].id == row.id) {
      val2 = (i + $.plush.queuecurpage * $.plush.queuePerPage);
      $.ajax({
        headers: {"Cache-Control": "no-cache"},
        type: "POST",
        url: "api",
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

  $.plush.InitQueueMultiOperations();

  }, // end $.plush.InitQueue()


  // ***************************************************************
  //  $.plush.InitQueueMultiOperations() - Queue Multi-Operation Events

  InitQueueMultiOperations : function() {

  // selections
  $("#multiops_select_all").click(function(){
    $("INPUT[type='checkbox']","#queueTable").prop('checked', true).trigger('change');
  });
  var last1, last2;
  $("#multiops_select_range").click(function(){
    if (last1 >= 0 && last2 >= 0 && last1 < last2)
      $("INPUT[type='checkbox']","#queueTable").slice(last1,last2).prop('checked', true).trigger('change');
    else if (last1 >= 0 && last2 >= 0)
      $("INPUT[type='checkbox']","#queueTable").slice(last2,last1).prop('checked', true).trigger('change');
  });
  $("#multiops_select_invert").click(function(){
    $("INPUT[type='checkbox']","#queueTable").each( function() {
      $(this).prop('checked', !$(this).prop('checked')).trigger('change');
    });
  });
  $("#multiops_select_none").click(function(){
    $("INPUT[type='checkbox']","#queueTable").prop('checked', false).trigger('change');
  });
  $("#queue").delegate('.multiops','change',function(event) {
    // range event interaction
    if (last1 >= 0) last2 = last1;
    last1 = $(event.target).parent()[0].rowIndex ? $(event.target).parent()[0].rowIndex : $(event.target).parent().parent()[0].rowIndex;

  // checkbox state persistence
  if ($(this).prop('checked'))
    $.plush.multiOpsChecks[$(this).parent().parent().attr('id')] = true;
  else if ($.plush.multiOpsChecks[$(this).parent().parent().attr('id')])
    delete $.plush.multiOpsChecks[$(this).parent().parent().attr('id')];
});
$("a","#multiops_inputs").click(function(e){
  // prevent button text highlighting
  e.target.onselectstart = function() { return false; };
  e.target.unselectable = "on";
  e.target.style.MozUserSelect = "none";
});

  // reset ui options
  $('#multi_reset').click(function(){
    $('#multi_status, #multi_cat, #multi_priority, #multi_pp, #multi_script').val('');
  });

  // apply options - cat/priority/pp/script
  $('#multi_apply').click(function(){

  var nzo_ids = "";
  $("INPUT[type='checkbox']:checked","#queueTable").each( function() {
    nzo_ids += "," + $(this).parent().parent().attr('id');
  });
  nzo_ids = nzo_ids.substr(1);
  if (!nzo_ids) return;

  $(this).prop('disabled',true);

  if ($('#multi_status').val())
    $.ajax({
      headers: {"Cache-Control": "no-cache"},
      type: "POST",
      url: "api",
      data: {mode:'queue', name:$('#multi_status').val(), value: nzo_ids, apikey: $.plush.apikey}
    });

  if ($('#multi_cat').val())
    $.ajax({
      headers: {"Cache-Control": "no-cache"},
      type: "POST",
      url: "api",
      data: {mode: 'change_cat', value: nzo_ids, value2: $('#multi_cat').val(), apikey: $.plush.apikey}
    });

  if ($('#multi_priority').val())
    $.ajax({
      headers: {"Cache-Control": "no-cache"},
      type: "POST",
      url: "api",
      data: {mode:'queue', name:'priority', value: nzo_ids, value2: $('#multi_priority').val(), apikey: $.plush.apikey}
    });

  if ($('#multi_pp').val())
    $.ajax({
      headers: {"Cache-Control": "no-cache"},
      type: "POST",
      url: "api",
      data: {mode: 'change_opts', value: nzo_ids, value2: $('#multi_pp').val(), apikey: $.plush.apikey}
    });

  if ($('#multi_script').val())
    $.ajax({
      headers: {"Cache-Control": "no-cache"},
      type: "POST",
      url: "api",
      data: {mode: 'change_script', value: nzo_ids, value2: $('#multi_script').val(), apikey: $.plush.apikey}
    });

  $(this).prop('disabled',false);
  $.plush.RefreshQueue();
});

  // nzb removal
  $('#multi_delete').click(function(){

  var nzo_ids = "";
  $("INPUT[type='checkbox']:checked","#queueTable").each( function() {
    nzo_ids += "," + $(this).parent().parent().attr('id');
  });
  nzo_ids = nzo_ids.substr(1);
  if (!nzo_ids) return;

  $('#delete_nzb_modal_title').text( $("INPUT[type='checkbox']:checked","#queueTable").size() + " NZBs" );
  $('#delete_nzb_modal_job').val( nzo_ids );
  $('#delete_nzb_modal_mode').val( 'queue' );
  $('#delete_nzb_modal_remove_files').button('enable');
  $.colorbox({ inline:true, href:"#delete_nzb_modal", title:$(this).text(),
    innerWidth:"600px", innerHeight:"150px", initialWidth:"600px", initialHeight:"150px", speed:0, opacity:0.7
  });
  return false;

/*
  if (!$.plush.confirmDeleteQueue || confirm($.plush.Tconfirmation)){
    $.ajax({
      type: "POST",
      url: "api",
      data: {mode:'queue', name:'delete', value: nzo_ids, apikey: $.plush.apikey},
      success: $.plush.RefreshQueue
    });
  }
*/
  });

  }, // end $.plush.InitQueueMultiOperations()


  // ***************************************************************
  //  $.plush.InitHistory() -- History Events

  InitHistory : function() {

  // Search
  $('#historySearchForm').submit(function(){
    $.plush.histcurpage = 0;
    $.plush.RefreshHistory();
    return false;
  });

  // Purge
  $('#hist_purge').click(function(event) {
    $.colorbox({ inline:true, href:"#history_purge_modal", title:$(this).text(),
      innerWidth:"375px", innerHeight:"250px", initialWidth:"375px", initialHeight:"250px", speed:0, opacity:0.7
    });
    return false;
  });
  $('#history_purge_modal input:submit').click(function(){
    var value = $(this).attr('name');
    var del_files=0
    if (value=="delete") {
      del_files=1;
      value="failed";
    }
    $.ajax({
      headers: {"Cache-Control": "no-cache"},
      type: "POST",
      url: "api",
      data: {mode:'history', name:'delete', value:value, del_files:del_files, search: $('#historySearchBox').val(), apikey: $.plush.apikey},
      success: function(){
        $.colorbox.close();
        $.plush.modalOpen=false;
        $.plush.RefreshHistory();
      }
    });
  });

  // refresh on mouseout after deletion
  $('#history').hover(  // $.mouseout was triggering too often
    function(){}, // over
    function(){   // out
      if ($.plush.pendingHistoryRefresh) {
        $.plush.pendingHistoryRefresh = false;
        $.plush.RefreshHistory();
      }
    }
  );

  // colorbox event bindings - so history doesn't refresh when viewing modal (thereby breaking rel prev/next)
  $(document).bind('cbox_open', function(){ $.plush.modalOpen=true; });
  $(document).bind('cbox_closed', function(){ $.plush.modalOpen=false; });
  $(document).bind('cbox_complete', function(){
    if ($('#cboxLoadedContent h3').text()) $('#cboxTitle').text( $('#cboxLoadedContent h3').text() );
    $('#cboxLoadedContent input[type=button], #cboxLoadedContent h3').hide(); // hide back button, title

  // fixed-width font for user-script log
  if ($.colorbox.element().hasClass('modal'))
    $('#cboxLoadedContent').css('font-family','Courier, monospace');
  else
    $('#cboxLoadedContent').css('font-family',"'Century Gothic', 'AppleGothic', sans-serif");
});

  // Set history per-page preference
  $("#history-pagination-perpage").val($.plush.histPerPage);
  $.plush.histcurpage = 0; // default 1st page

  // Pagination per-page selection
  $("#history-pagination-perpage").change(function(event){
    $.plush.histcurpage = Math.floor($.plush.histcurpage * $.plush.histPerPage / $(event.target).val() );
    $.plush.histPerPage = $(event.target).val();
    $.cookie('plushHistPerPage', $.plush.histPerPage, { expires: 365 });
    $.plush.histforcerepagination = true;
    if ($.plush.histPerPage=="1")
      $("#history-pagination").html(''); // pagination rebuild not triggered on blank history (disabled)
    $.plush.RefreshHistory();
  });

  // nzb retry, click 'add nzb' link to show upload form
  $('#history .retry-nzbfile').live('click',function(){
    $('#retry_modal_title').text( $(this).parent().parent().prev().children('a:first').text() );
    $('#retry_modal_job').val( $(this).parent().parent().parent().attr('id') );
    $.colorbox({ inline:true, href:"#retry_modal", title:$(this).text(),
      innerWidth:"375px", innerHeight:"350px", initialWidth:"375px", initialHeight:"350px", speed:0, opacity:0.7
    });
    return false;
  });

  // NZB individual removal
  $('#history').delegate('.sprite_ql_cross','click', function(event) {
    $('#delete_nzb_modal_title').text( $(this).parent().prev().prev().children('a:first').text() );
    $('#delete_nzb_modal_job').val( $(this).parent().parent().attr('id') );
    $('#delete_nzb_modal_mode').val( 'history' );
    if ($(this).parent().parent().children('td:first').children().hasClass('sprite_hv_star'))
      $('#delete_nzb_modal_remove_files').button('disable');
    else
      $('#delete_nzb_modal_remove_files').button('enable');
    $.colorbox({ inline:true, href:"#delete_nzb_modal", title:$(this).text(),
      innerWidth:"600px", innerHeight:"150px", initialWidth:"600px", initialHeight:"150px", speed:0, opacity:0.7
    });
    return false;
  });

//      if (!$.plush.confirmDeleteHistory || confirm($.plush.Tconfirmation)){

  $('#delete_nzb_modal_remove_nzb, #delete_nzb_modal_remove_files','#delete_nzb_modal').click(function(e){
    var del_files=0;
    if ($(this).attr('id')=="delete_nzb_modal_remove_files")
      del_files=1;

  delid = $('#delete_nzb_modal_job').val();
  mode = $('#delete_nzb_modal_mode').val();
  $('#'+delid).fadeTo('normal',0.25);
  $.plush.pendingHistoryRefresh = true;
  $.colorbox.close();
  $.ajax({
    headers: {"Cache-Control": "no-cache"},
    type: "POST",
    url: "api",
    data: {mode:mode, name:'delete', value: delid, del_files: del_files, apikey: $.plush.apikey},
    success: function(){
      if ( $("#historyTable tr:visible").length - 1 < 1 ) { // don't leave stranded on non-page
        $.plush.histforcerepagination = true;
        $.plush.RefreshHistory($.plush.histcurpage-1);
      }
      if ( $("#queueTable tr:visible").length - 1 < 1 ) { // don't leave stranded on non-page
        $.plush.skipRefresh = false;
        $.plush.queueforcerepagination = true;
        $.plush.RefreshQueue($.plush.queuecurpage-1);
      }
      if (delid.indexOf(','))
        $.plush.RefreshQueue();
    }
  });
  return false;
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

  // show all / show failed
  $('#failed_only').change(function(){
    $.plush.failedOnly = $("#failed_only").val();
    $.cookie('plushFailedOnly', $.plush.failedOnly, { expires: 365 });
    $.plush.RefreshHistory();
  }).val($.plush.failedOnly);

  // Sustained binding of events for elements added to DOM
  $('#historyTable').livequery(function() {

  // modal for viewing script logs
  $('#historyTable .modal').colorbox({ innerWidth:"80%", innerHeight:"80%", initialWidth:"80%", initialHeight:"80%", speed:0, opacity:0.7 });
  $("#historyTable .modal-detail").colorbox({ inline:true,
    href: function(){return "#details-"+$(this).parent().parent().attr('id');},
    title:function(){return $(this).text().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;");},
    innerWidth:"80%", innerHeight:"300px", initialWidth:"80%", initialHeight:"300px", speed:0, opacity:0.7 });

  // modal for reporting issues
  $("#historyTable .modal-report").colorbox({ inline:true,
    href: function(){return "#report-"+$(this).parent().parent().parent().attr('id');},
    title:function(){return $(this).text();},
    innerWidth:"250px", innerHeight:"110px", initialWidth:"250px", initialHeight:"110px", speed:0, opacity:0.7 });

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
    num_display_entries: 4,
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

  $('.user_combo').livequery('change', function(){
    var nzo_id = $(this).parent().parent().parent().parent().attr('id');
    var videoAudio = $(this).hasClass('video') ? 'video' : 'audio';
    $.ajax({
      headers: {"Cache-Control": "no-cache"},
      type: "POST",
      url: "api",
      data: {mode:'queue', name:'rating', value: nzo_id, type: videoAudio, setting: $(this).val(), apikey: $.plush.apikey},
      success: $.plush.Refresh
    });
  });

  $('.user_vote').livequery('click', function(){
    var nzo_id = $(this).parent().parent().parent().attr('id');
    var upDown = $(this).hasClass('up') ? 'up' : 'down';
    $.ajax({
      headers: {"Cache-Control": "no-cache"},
      type: "POST",
      url: "api",
      data: {mode:'queue', name:'rating', value: nzo_id, type: 'vote', setting: upDown, apikey: $.plush.apikey},
      success: $.plush.Refresh
    });
  });

  $('#history .show_flags').live('click', function(){
    $('#flag_modal_job').val( $(this).parent().parent().parent().attr('id') );
    $.colorbox({ inline:true, href:"#flag_modal", title:$(this).text(),
      innerWidth:"500px", innerHeight:"185px", initialWidth:"500px", initialHeight:"185px", speed:0, opacity:0.7
    });
    return false;
  });
  $('#flag_modal input:submit').click(function(){
    var nzo_id = $('#flag_modal_job').val();
    var flag = $('input[name=rating_flag]:checked', '#flag_modal').val();
    var expired_host = $('input[name=expired_host]', '#flag_modal').val();
    var other = $('input[name=other]', '#flag_modal').val();
    var comment = $('input[name=comment]', '#flag_modal').val();
    var _detail = (flag == 'comment') ? comment : ((flag == 'other') ? other : expired_host);
    $.colorbox.close();
    $.plush.modalOpen=false;
    $.ajax({
      headers: {"Cache-Control": "no-cache"},
      type: "POST",
      url: "api",
      data: {mode:'queue', name:'rating', value: nzo_id, type: 'flag', setting: flag, detail: _detail, apikey: $.plush.apikey},
      success: $.plush.RefreshHistory
    });
  });

  }, // end $.plush.InitHistory()


  // ***************************************************************
  //  $.plush.Refresh()

  Refresh : function(force) {

  clearTimeout($.plush.timeout);  // prevent back-to-back refreshes

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
  //  $.plush.RefreshQueue() -- fetch HTML data from queue.tmpl

  RefreshQueue : function(page) {

  // Skip refresh if cursor hovers queue, to prevent UI annoyance
  if ($.plush.blockRefresh && $.plush.skipRefresh) {
    $.plush.pendingQueueRefresh = true;
    return $('#manual_refresh_wrapper').addClass('refresh_skipped');
  }

  // no longer a need for a pending queue refresh (associated with nzb deletions)
  $.plush.pendingQueueRefresh = false;

  // Deal with pagination for start/limit
  if (typeof( page ) == 'undefined' || page == "ok\n" || page < 0 )
    page = $.plush.queuecurpage;
  else if (page != $.plush.queuecurpage)
    $.plush.queuecurpage = page;

  // Refresh state notification
  $('#manual_refresh_wrapper').removeClass('refresh_skipped').addClass('refreshing');

  if ($('#queueSearchBox').val() )
    var data = {start: 0, limit: 0, search: $('#queueSearchBox').val() };
  else
    var data = {start: ( page * $.plush.queuePerPage ), limit: $.plush.queuePerPage};

  // Fetch updated content from queue.tmpl
  $.ajax({
    headers: {"Cache-Control": "no-cache"},
    type: "POST",
    url: "queue/",
    data: data,
    success: function(result){
      if (!result) {
        $('#manual_refresh_wrapper').addClass('refresh_skipped'); // Failed refresh notification
        return;
      }

      $('.left_stats .initial-loading').hide();
      $('#queue').html(result);               // Replace queue contents with queue.tmpl
      $('#queue .avg_rate').rateit({readonly: true, resetable: false, step: 0.5});
      $('#queue .avg_rate').each(function() { $(this).rateit('value', $(this).attr('value') / 2); });

      if ($.plush.multiOps) // add checkboxes
        $('<input type="checkbox" class="multiops" />').appendTo('#queue tr td.nzb_status_col');
      if ($.plush.multiOpsChecks) // checkbox state persistence
        for (var nzo_id in $.plush.multiOpsChecks)
          $('#'+nzo_id+' .multiops').prop('checked',true);

      $('#queue-pagination span').removeClass('loading');   // Remove spinner graphic from pagination
      $('#manual_refresh_wrapper').removeClass('refreshing'); // Refresh state notification
    },
    error: function(xhr){
      // Only reason for a 404 error could be a login failure -> redirect
      if(xhr.status == 404) {
        document.location=document.location;
      }
    }
  });

  }, // end $.plush.RefreshQueue()



  // ***************************************************************
  //  $.plush.SetQueueStats(str) -- called from queue.tmpl
  SetQueueStats : function(str) {
    $('#queue_stats').html(str);
  },


  // ***************************************************************
  //  $.plush.SetQueueStats(str) -- called from queue.tmpl
  SetQueueStats : function(str) {
    $('#queue_stats').html(str);
  },


  // ***************************************************************
  //  $.plush.RefreshHistory() -- fetch HTML data from history.tmpl (AHAH)

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
    var data = {failed_only: $.plush.failedOnly, start: 0, limit: 0, search: $('#historySearchBox').val() };
  else if ($('#historySearchBox').val())
    var data = {failed_only: $.plush.failedOnly, start: ( page * $.plush.histPerPage ), limit: $.plush.histPerPage, search: $('#historySearchBox').val() };
  else
    var data = {failed_only: $.plush.failedOnly, start: ( page * $.plush.histPerPage ), limit: $.plush.histPerPage};



  $.ajax({
    headers: {"Cache-Control": "no-cache"},
    type: "POST",
    url: "history/",
    data: data,
    success: function(result){
      if (!result) {
        $('#manual_refresh_wrapper').addClass('refresh_skipped'); // Failed refresh notification
        return;
      }
      $('.left_stats .initial-loading').hide();
      $('#history').html(result);               // Replace history contents with history.tmpl
      $('#history .avg_rate').rateit({readonly: true, resetable: false, step: 0.5});
      $('#history .avg_rate').each(function() { $(this).rateit('value', $(this).attr('value') / 2); });
      $('#history .user_combo option').filter(function() {
        return $(this).attr('value') == $(this).parent().parent().find('input.user_combo').attr('value');
      }).attr('selected', true);
      $('#history-pagination span').removeClass('loading'); // Remove spinner graphic from pagination
    }
  });

  }, // end $.plush.RefreshHistory()


  // ***************************************************************
  //  $.plush.SetQueueStats(str) -- called from queue.tmpl
  SetQueueStats : function(str) {
    $('#queue_stats').html(str);
  },


  // ***************************************************************
  //  $.plush.SetQueueSpeedLimit(str) -- called from queue.tmpl
  SetQueueSpeedLimit : function(speedLimit, speedLimitAbs) {
    // For switching using the select
    if(!speedLimit) speedLimit = $.plush.speedLimit;
    if(speedLimitAbs == undefined) speedLimitAbs = $.plush.speedLimitAbs;

    // Save
    $.plush.speedLimit = speedLimit;
    $.plush.speedLimitAbs = speedLimitAbs;

    // How do we format?
    switch($.plush.speedLimitType) {
        case '%':
            speedlimitDisplay = speedLimit;
            break;
        case 'K':
            // Only whole KB/s
            speedlimitDisplay = Math.round(speedLimitAbs/1024);
            break;
        case 'M':
            speedlimitDisplay = speedLimitAbs/1024/1024;
            break;
    }

    // In case nothing and we make the displaying of the float more pretty
    speedlimitDisplay = (isNaN(speedlimitDisplay) || speedlimitDisplay == '0') ? '' : speedlimitDisplay;
    speedlimitDisplay = Math.round(speedlimitDisplay*10)/10;

    // Update
    if ($("#maxSpeed-option").val() != speedlimitDisplay && !$.plush.focusedOnSpeedChanger)
      $("#maxSpeed-option").val(speedlimitDisplay);
    if (speedlimitDisplay && speedlimitDisplay!="")
      $('#speed-wrapper .sprite_q_menu_pausefor').addClass('sprite_q_menu_pausefor_on');
    else
      $('#speed-wrapper .sprite_q_menu_pausefor').removeClass('sprite_q_menu_pausefor_on');
  },


  // ***************************************************************
  //  $.plush.SetQueueFinishAction(str) -- called from queue.tmpl
  SetQueueFinishAction : function(str) {
    if ($("#onQueueFinish-option").val() != str)
      $("#onQueueFinish-option").val(str);
    if (str && str!="")
      $('.sprite_q_queue').addClass('sprite_q_queue_on');
    else
      $('.sprite_q_queue').removeClass('sprite_q_queue_on');
  },


  // ***************************************************************
  //  $.plush.SetQueuePauseInfo(paused,str) -- called from queue.tmpl
  SetQueuePauseInfo : function(paused,str) {
    $.plush.paused = paused;

  // Pause/resume button state
  if ( paused && !$('#pause_resume').hasClass('sprite_q_pause_on') )
    $('#pause_resume').removeClass('sprite_q_pause').addClass('sprite_q_pause_on');
  else if ( !paused && !$('#pause_resume').hasClass('sprite_q_pause') )
    $('#pause_resume').removeClass('sprite_q_pause_on').addClass('sprite_q_pause');

  // Pause interval
  if (str && str!="" && str!="0") {
    $('#pause_int').html(str);
    $('.queue-buttons-pause .sprite_q_menu_pausefor').addClass('sprite_q_menu_pausefor_on');
  } else {
    $('#pause_int').html("")
    $('.queue-buttons-pause .sprite_q_menu_pausefor').removeClass('sprite_q_menu_pausefor_on');
  }
},


  // ***************************************************************
  //  $.plush.SetQueueETAStats(speed,kbpersec,timeleft,eta) -- called from queue.tmpl
  SetQueueETAStats : function(speed,kbpersec,timeleft,eta) {

  // ETA/speed stats at top of queue
  if (kbpersec < 100 && $.plush.paused) {
    $('#stats_eta').html('&mdash;');
    $('#stats_speed').html('&mdash;');
    $('#time-left').attr('title','&mdash;');  // Tooltip on "time left"
  }
  else {
    $('#stats_eta').html(timeleft);
    $('#stats_speed').html(speed+"B/s");
    $('#time-left').attr('title',eta);  // Tooltip on "time left"
  }
},


  // ***************************************************************
  //  $.plush.SetWarnings(have_warnings,last_warning) -- called from queue.tmpl
  SetWarnings : function(have_warnings,last_warning) {
    $('#have_warnings').html(have_warnings);    // Update warnings count/latest warning text in main menu
    $('#last_warning').attr('title',last_warning);
    if (have_warnings > 0) {
      $('#warning_box').show();
    } else {
      $('#warning_box').hide();
    }
  },


  // ***************************************************************
  //  $.plush.SetLoadavg(str) -- called from history.tmpl
  SetLoadavg : function(str) {
    $('#loadavg').html(str);
  },

  // ***************************************************************
  //  $.plush.SetHistoryStats(str) -- called from history.tmpl
  SetHistoryStats : function(str) {
    $('#history_stats').html(str);
  }

  }; // end $.plush object

});

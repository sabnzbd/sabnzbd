// *****************************************************************
// Plush Config code as follows, by pairofdimes (see LICENSE-CC.txt)

jQuery(document).ready(function($){

  // Top Menu
  var noTopMenu = $.cookie('plushNoTopMenu')  ? $.cookie('plushNoTopMenu')  : 0;
  $('#topmenu_bar').show();

  // Container width
  var containerWidth = $.cookie('plushContainerWidth')  ? $.cookie('plushContainerWidth')  : '100%';
  $('#master-width').css('width',containerWidth);

  // Confirm user exits without saving changes first
  if (config_pane != 'NZO') {
    $(':input','form').change(function(){
      window.onbeforeunload = function(){return confirmWithoutSavingPrompt;}
    });
    $('form').submit(function(){
      window.onbeforeunload = null;
    });
  }

  // modals
  $("#help").colorbox({ inline:true, href:"#help_modal", title:$("#help").text(),
    innerWidth:"375px", innerHeight:"350px", initialWidth:"375px", initialHeight:"350px", speed:0, opacity:0.7
  });
  $(".show_qrcode").colorbox({ photo:true, innerHeight:"300px", innerWidth:"300px", speed:0, opacity: 0.7, scrolling:false });

  // jqueryui tabs/buttons
  $('.juiButton').button();
  $( ".tabs" ).tabs({
    cookie: {
      expires: 1 // store cookie for a day, without, it would be a session cookie
    }
  });
  $(".vertical-tabs").tabs().addClass('ui-tabs-vertical ui-helper-clearfix');
  $(".vertical-tabs li").removeClass('ui-corner-top').addClass('ui-corner-left');

  // kludge for jqueryui tabs, using cookie option above for some reason does not select the default 1st tab
  $('.tabs').each(function(index) {
    if (!$(this).children('ul.ui-tabs-nav').children('li.ui-tabs-selected').length)
      $(this).tabs('select',0);
  });

  // kludge for jqueryui tabs, clicking for an existing tab doesnt switch to it
  $('#activeFeedLink').click(function(){
    // tab-feed focus
    $( ".tabs" ).tabs("select",1)
    return false;
  });

  switch(config_pane) {

  // not a config page, rather queued nzb file listing page
  case 'NZO':
    $('#nzo_reload').click(function(){ document.location.reload(); });

  // operations
  $('#nzo_delete').click(function(){
    $('#action_key').val('Delete');
    $('#bulk_operation').submit();
  });
  $('#nzo_top').click(function(){
    $('#action_key').val('Top');
    $('#bulk_operation').submit();
  });
  $('#nzo_up').click(function(){
    $('#action_key').val('Up');
    $('#bulk_operation').submit();
  });
  $('#nzo_down').click(function(){
    $('#action_key').val('Down');
    $('#bulk_operation').submit();
  });
  $('#nzo_bottom').click(function(){
    $('#action_key').val('Bottom');
    $('#bulk_operation').submit();
  });

  // selections
  $("#nzo_select_all").click(function(){
    $("INPUT[type='checkbox']").prop('checked', true).trigger('change');
  });
  var last1, last2;
  $("#nzo_select_range").click(function(){
    if (last1 && last2 && last1 < last2)
      $("INPUT[type='checkbox']").slice(last1,last2).prop('checked', true).trigger('change');
    else if (last1 && last2)
      $("INPUT[type='checkbox']").slice(last2,last1).prop('checked', true).trigger('change');
  });
  $("#nzo_select_invert").click(function(){
    $("INPUT[type='checkbox']").each( function() {
      $(this).prop('checked', !$(this).prop('checked')).trigger('change');
    });
  });
  $("#nzo_select_none").click(function(){
    $("INPUT[type='checkbox']").prop('checked', false).trigger('change');
  });

  // click filenames to select
  $('#config_content .nzoTable .nzf_row').click(function(event) {
    $('#box-'+$(event.target).parent().attr('id')).prop('checked', !$('#box-'+$(event.target).parent().attr('id')).prop('checked')).trigger('change');

  // range event interaction -- see further above
  if (last1) last2 = last1;
  last1 = $(event.target).parent()[0].rowIndex ? $(event.target).parent()[0].rowIndex : $(event.target).parent().parent()[0].rowIndex;
});

  //
  $('#config_content .nzoTable .nzf_row input').change(function(e){
    if ($(e.target).prop('checked'))
      $(e.target).parent().parent().addClass("nzo_highlight");
    else
      $(e.target).parent().parent().removeClass("nzo_highlight");
  });

  // set highlighted property for checked rows upon reload
  $('#config_content .nzoTable .nzf_row input:checked').parent().parent().addClass("nzo_highlight");

  return; // skip the rest of the config methods
  break;


  case 'Status':
    $('#logging_level').change(function(event){
      window.location = './change_loglevel?loglevel='+$(event.target).val()+'&apikey='+apikey;
    });
    break;

  case 'General':
    $('#apikey').click(function(){ $('#apikey').select() });
    $('#generate_new_apikey').click(function(){
      if (confirm($(this).attr('rel'))) {
        $.ajax({
          type: "POST",
          url: "../../api",
          data: {mode:'config', name:'set_apikey', apikey: $('#apikey').val()},
          success: function(msg){
            $('#apikey,#session').val(msg);
            window.location.reload();
          }
        });
      }
    });
    $('#generate_new_nzbkey').click(function(){
      if (confirm($(this).attr('rel'))) {
        $.ajax({
          type: "POST",
          url: "../../api",
          data: {mode:'config', name:'set_nzbkey', apikey: $('#apikey').val()},
          success: function(msg){
            $('#nzbkey,#session').val(msg);
            window.location.reload();
          }
        });
      }
    });
    $('#sabnzbd_restart').click(function(){
      return confirm($(this).attr('rel'));
    });
    break;

  case 'Servers':
    $('form .testServer').click(function(event){ // test server
      $(event.target).next('span').addClass('loading');
      $.ajax({
        type: "POST",
        url: "../../api",
        data: "mode=config&name=test_server&"+ $(event.target).parents('form:first').serialize() +"&apikey="+$('#apikey').val(),
        success: function(msg){
          alert(msg);
          $(event.target).next('span').removeClass('loading');
        }
      });
    });
    $('form .delServer').click(function(event){ // delete server
      if(confirm($(event.target).attr('rel')))
        $(event.target).parents('form:first').attr('action','delServer').submit();
      return false;
    });
    $('form .clrServer').click(function(event){ // clear server
      if(confirm($(event.target).attr('rel')))
        $(event.target).parents('form:first').attr('action','clrServer').submit();
      return false;
    });
    break;

  case 'Categories':
    $(':button').click(function(event){ // delete category
      window.location="delete/?name="+$(event.target).attr('name')+'&apikey='+apikey;
    });
    break;

  case 'RSS':

  $('.toggleFeedCheckbox').click(function(){  // enable/disable feed
    window.onbeforeunload = null; // lose data?
    this.form.action='toggle_rss_feed?apikey=$apikey';
    this.form.submit();
    return false;
  });
  $('.rssOrderSelect').change(function(){ // change filter order
    window.onbeforeunload = null; // lose data?
    location = this.options[this.selectedIndex].value;
  });
  break;

  case 'Email':
    $('#test_email').click(function(){
      return confirm($('#test_email').attr('rel'));
    });
    break;

  case 'Index Sites':
    $('#getBookmarks').click(function(){ window.location='getBookmarks?apikey='+apikey; });
    $('#hideBookmarks').click(function(){ window.location='hideBookmarks?apikey='+apikey; });
    $('#showBookmarks').click(function(){ window.location='showBookmarks?apikey='+apikey; });
    break;

  case 'Sorting':
    previewtv(); previewmovie(); previewdate(); // display sorting previews -- these functions are defined below
    break;

  };

  // page's save button for those pages that use it
  $('#save').click(function(){
    window.onbeforeunload = null;
    $('form').submit();
  });

}); // end Plush code

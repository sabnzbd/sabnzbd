// *****************************************************************
// Plush Config code as follows, by pairofdimes (see LICENSE-CC.txt)

jQuery(document).ready(function($){

    // rounding
/*	if ($.browser.safari) { // slow down rounding just a hair for Safari or it spazzes out
		setTimeout (function(){
	    	$('.config_nav li a').corner("round tl bl");
	    	$('#config_container').corner("round");
	    	$('#config_content legend').corner("round");
	    	$('#force_disconnect, #save, #sabnzbd_restart, #test_email, #help').corner("round");
		}, 50);
	} else { // the slight delay lags on Firefox, so don't run otherwise
	    	$('.config_nav li a').corner("round tl bl");
	    	$('#config_container').corner("round");
	    	$('#config_content legend').corner("round");
	    	$('#force_disconnect, #save, #sabnzbd_restart, #test_email, #help').corner("round");
	}*/

	// Confirm user exits without saving changes first
	if (config_pane != 'NZO') {
	    $(':input','form').change(function(){
			window.onbeforeunload = function(){return confirmWithoutSavingPrompt;}
		});
		$('form').submit(function(){
			window.onbeforeunload = null;
		});
	}
	
	// jqueryui tabs/buttons
	$('.juiButton').button();
	$( ".tabs" ).tabs({
		cookie: {
			expires: 1 // store cookie for a day, without, it would be a session cookie
		}
	});
	// kludge for jqueryui tabs, clicking for an existing tab doesnt switch to it
	$('#activeFeedLink').click(function(){
		// tab-feed focus
		$( ".tabs:first" ).tabs("select",3)
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
	            $("INPUT[type='checkbox']").attr('checked', true).trigger('change');
	        });
	        var last1, last2;
	        $("#nzo_select_range").click(function(){
	        	if (last1 && last2 && last1 < last2)
		            $("INPUT[type='checkbox']").slice(last1,last2).attr('checked', true).trigger('change');
		        else if (last1 && last2)
		            $("INPUT[type='checkbox']").slice(last2,last1).attr('checked', true).trigger('change');
	        });
	        $("#nzo_select_invert").click(function(){
	            $("INPUT[type='checkbox']").each( function() {
	                $(this).attr('checked', !$(this).attr('checked')).trigger('change');
	            });
	        });
	        $("#nzo_select_none").click(function(){
	            $("INPUT[type='checkbox']").attr('checked', false).trigger('change');
	        });

	        // click filenames to select
	        $('#config_content .nzoTable .nzf_row').click(function(event) {
	            $('#box-'+$(event.target).parent().attr('id')).attr('checked', !$('#box-'+$(event.target).parent().attr('id')).attr('checked')).trigger('change');
	            
	            // range event interaction -- see further above
	            if (last1) last2 = last1;
	            last1 = $(event.target).parent()[0].rowIndex ? $(event.target).parent()[0].rowIndex : $(event.target).parent().parent()[0].rowIndex;
	        });

			// 
			$('#config_content .nzoTable .nzf_row input').change(function(e){
				if ($(e.target).attr('checked'))
					$(e.target).parent().parent().addClass("nzo_highlight");
				else
					$(e.target).parent().parent().removeClass("nzo_highlight");
			});
	        
	        // set highlighted property for checked rows upon reload
			$('#config_content .nzoTable .nzf_row input:checked').parent().parent().addClass("nzo_highlight");

	        return; // skip the rest of the config methods
			break;
        
        
        case 'Connections':
        	$('#logging_level').change(function(event){
				window.location = './change_loglevel?loglevel='+$(event.target).val()+'&session='+apikey;
			});
			break;
        
        case 'General':
			$('#apikey').click(function(){ $('#apikey').select() });
			$('#generate_new_apikey').click(function(){
				$.ajax({
					type: "POST",
					url: "../../tapi",
					data: {mode:'config', name:'set_apikey', apikey: $('#apikey').val()},
					success: function(msg){
						$('#apikey').val(msg);
						$('#hiddenSession').val(msg);
					}
				});
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
					url: "../../tapi",
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
			break;

        case 'Categories':
        	$(':button').click(function(event){ // delete category
        		window.location="delete/?name="+$(event.target).attr('name')+'&session='+apikey;
        	});
        	break;

        case 'RSS':
			/*
        	$(':checkbox').click(function(event){ // toggle feed
				$(event.target).parents('form:first').attr('action','toggle_rss_feed').submit();
				return false;
			});
        	$('#config_content .EntryFieldSet .preview_feed').click(function(event){
				$.fn.colorbox({
					href:'test_rss_feed?'+$(event.target).parents('form:first').serialize(),
					innerWidth:"80%", innerHeight:"80%", initialWidth:"80%", initialHeight:"80%", speed:0, opacity:0.7
				});
				return false;
			});
			$(document).bind('cbox_complete', function(){
				$('#cboxTitle').text( $('#cboxLoadedContent h3').text() );
				$('#cboxLoadedContent input, #cboxLoadedContent h3').hide(); // hide back button, title
				$('#cboxLoadedContent a').click(function(event){
					if( $(event.target).attr('target') != '_blank' ) {
						$.ajax({ url: $(event.target).attr('href') }); // ajax downloads
						$(event.target).replaceWith('Download');
						return false;
					}
				});
			});
        	$('#config_content .EntryFieldSet .download_feed').click(function(event){
				if(confirm($(event.target).attr('rel'))) {
					$.fn.colorbox({
						href:'download_rss_feed?'+$(event.target).parents('form:first').serialize(),
						innerWidth:"80%", innerHeight:"80%", initialWidth:"80%", initialHeight:"80%", speed:0, opacity:0.7
					});
				}
				return false;
			});
        	$('#config_content .EntryFieldSet .delete_feed').click(function(event){
				if(confirm($(event.target).attr('rel')))
					$(event.target).parents('form:first').attr('action','del_rss_feed').submit();
				return false;
			});
        	$('#config_content .EntryFieldSet .filter_order').change(function(event){ // update filter order
        		window.onbeforeunload = null;
				window.location = $(event.target).val()+'&session='+apikey;
			});
			*/
			break;

        case 'Email':
            $('#test_email').click(function(){
				return confirm($('#test_email').attr('rel'));
		    });
		    break;
        	
        case 'Index Sites':
        	$('#getBookmarks').click(function(){ window.location='getBookmarks?session='+apikey; });
        	$('#hideBookmarks').click(function(){ window.location='hideBookmarks?session='+apikey; });
        	$('#showBookmarks').click(function(){ window.location='showBookmarks?session='+apikey; });
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

$(document).ready(function(){
	
	$('.config_menu').corner("round tl bl");
	$('#config_container').corner("round");
	$('#help').corner("round");
	
	switch(config_pane) {
		case 'Connections':
			$('#test_email').corner("round");
			$('#force_disconnect').corner("round");
			break;
		case 'Sorting':
			previewtv();
		case 'General':
		case 'Folders':
		case 'Switches':
		case 'Email':
		case 'Index Sites':
			$('#save').corner("round");
			break;
	};

});

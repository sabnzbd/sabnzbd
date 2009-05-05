function toggleWebPass()
{
    var web
    web = $('#enable_webpass').attr('checked')
    if ($('#enable_webpass').attr('checked') == 1)
    {
        $('#web_user').attr("disabled","");
        $('#web_pass').attr("disabled","");
        
    } else {
        $('#web_user').attr("disabled","disabled");
        $('#web_pass').attr("value","");
        $('#web_pass').attr("disabled","disabled");
        $('#web_user').attr("value","");
    }
};

$(document).ready(function() {
    toggleWebPass();
    $('#enable_webpass').bind('change click focus', function() {
    toggleWebPass();
    });
});
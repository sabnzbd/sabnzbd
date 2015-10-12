function checkRequired() {
    if ($("#host").val() && $("#connections").val()) {
        $("#next-button").removeClass('disabled')
        return true;
    } else {
        $("#next-button").addClass('disabled')
        return false;
    }
}

$(document).ready(function() {
    // Add tooltips
    $('[data-toggle="tooltip"]').tooltip()
    
    // On form-submit
    $("#serverTest").click(function() {
        $('#serverResponse').html(txtChecking);
        $.getJSON(
            "../tapi?mode=config&name=test_server&output=json",
            $("form").serialize(),
            function(result) {
                if (result.value.result) {
                    r = '<span class="success"><span class="glyphicon glyphicon-ok"></span> ' + result.value.message + '</span>';
                } else {
                    r = '<span class="failed"><span class="glyphicon glyphicon-minus-sign"></span> ' + result.value.message + '</span>';
                }
                
                $('#serverResponse').html(r);
            }
        );
        return false;
    });

    $("#port, #connections").bind('keyup blur', function() {
        if (this.value > 0) {
            $(this).removeClass("incorrect");
            $(this).addClass("correct");
        } else {
            $(this).removeClass("correct");
            $(this).addClass("incorrect");
        }
        checkRequired()
    });

    $("#host, #username, #password").bind('keyup blur', function() {
        if (this.value) {
            $(this).removeClass("incorrect");
            $(this).addClass("correct");
        } else {
            $(this).removeClass("correct");
            $(this).addClass("incorrect");
        }
        checkRequired();
    });
    
    $('#ssl').click(function() {
        if(this.checked) {
            // Enabled SSL change port when not already a custom port
            if($('#port').val() == '119') {
                $('#port').val('563')
            }
        } else {
            // Remove SSL port
            if($('#port').val() == '563') {
                $('#port').val('119')
            }
        }
    })
    
    checkRequired() 
    
    $('form').submit(function(event) {
        // Double check
        if(!checkRequired()) {
            event.preventDefault();
        }
    })  
});
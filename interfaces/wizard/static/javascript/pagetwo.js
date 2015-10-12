function checkRequired() {
    if ($("#bandwidth").val()) {
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
    
    // Check
    $("#bandwidth").bind('keyup blur', function() {
        if (this.value) {
            $(this).removeClass("incorrect");
            $(this).addClass("correct");
            $("#bandwidth-error").addClass("hidden");          
        } else {
            $(this).removeClass("correct");
            $(this).addClass("incorrect");
            $("#bandwidth-error").removeClass("hidden");           
        }
        checkRequired()  
    });
    
    checkRequired() 
    
    $('form').submit(function(event) {
        // Double check
        if(!checkRequired()) {
            event.preventDefault();
        }
    })   
});


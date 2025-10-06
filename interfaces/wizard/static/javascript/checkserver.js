// Variable to track server test results
var serverTestSuccessful = false;

function resetTestResult() {
    serverTestSuccessful = false;
    $('#serverResponse').html(txtTestServer);
    checkRequired();
}

function setTestResult(success) {
    serverTestSuccessful = success;
    checkRequired();
}

function checkRequired() {
    // Check if form is valid using HTML5 validation and if server test passed
    if ($("form").get(0).checkValidity() && serverTestSuccessful) {
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

    // On server test button click
    $("#serverTest").click(function() {
        // Check HTML5 form validation before testing server
        if (!$("form").get(0).reportValidity()) {
            return false;
        }
        
        $('#serverResponse').html(txtChecking);
        $.getJSON(
            "../api?mode=config&name=test_server&output=json",
            $("form").serialize(),
            function(result) {
                if (result.value.result) {
                    r = '<span class="success"><span class="glyphicon glyphicon-ok"></span> ' + result.value.message + '</span>';
                    setTestResult(true);
                } else {
                    r = '<span class="failed"><span class="glyphicon glyphicon-minus-sign"></span> ' + result.value.message + '</span>';
                    setTestResult(false);
                }
                r = r.replace('https://sabnzbd.org/certificate-errors', '<a href="https://sabnzbd.org/certificate-errors" class="failed" target="_blank">https://sabnzbd.org/certificate-errors</a>')
                $('#serverResponse').html(r);
            }
        );
        return false;
    });

    // Reset test result when any form field changes
    $("#host, #username, #password, #port, #connections, #ssl_verify").bind('input change', function() {
        resetTestResult();
    });

    $('#ssl').click(function() {
        if(this.checked) {
            // Enabled SSL change port when not already a custom port
            if($('#port').val() === '119') {
                $('#port').val('563')
            }
        } else {
            // Remove SSL port
            if($('#port').val() === '563') {
                $('#port').val('119')
            }
        }
        resetTestResult();
    })

    checkRequired()

    $('form').submit(function(event) {
        // Check if server test passed (HTML5 validation is automatic)
        if(!serverTestSuccessful) {
            event.preventDefault();
        }
    })
});
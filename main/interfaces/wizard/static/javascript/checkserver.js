$(document).ready(function() {
    $("#serverTest").click(function(){
        $('#serverResponse').html('Checking...');
        $.ajax({
            type: "POST",
            url: "servertest",
            data: $("form").serialize(),
            success: function(result){
                if (result == "Connected Successfully!"){
                    cls = "success"
                } else {
                    cls = "failed"
                }
                r = '<span class="' + cls + '">' + result + '</span>';
                $('#serverResponse').html(r);
            }
        });
    });
    $(".validate-text").blur(function(){
        if (this.value || this.checked){
            $(this).removeClass("incorrect");
            $(this).addClass("correct");
        } else {
            $(this).removeClass("correct");
        }
    });
    $(".validate-text-required").blur(function(){
        if (this.value || this.checked){
            $(this).removeClass("incorrect");
            $(this).addClass("correct");
        } else {
            $(this).removeClass("correct");
            $(this).addClass("incorrect");
        }
    });
    $(".validate-numeric").blur(function(){
        if (this.value && isFinite(this.value)){
            $(this).removeClass("incorrect");
            $(this).addClass("correct");
        } else {
            $(this).removeClass("correct");
        }
    });
    $(".validate-numeric-required").blur(function(){
        if (this.value && isFinite(this.value)){
            $(this).removeClass("incorrect");
            $(this).addClass("correct");
        } else {
            $(this).removeClass("correct");
            $(this).addClass("incorrect");
        }
    });
});
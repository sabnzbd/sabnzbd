function checkRequired()
{
    if ($("#host").val() && $("#connections").val())
    {
        $("#next-button").removeAttr("disabled");
    } else {
        $("#next-button").attr("disabled","disabled");
    }
}

$(document).ready(function() {
    checkRequired()
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
    
    $("#connections").bind('keyup blur',function(){
        if (this.value && isFinite(this.value)){
            $(this).removeClass("incorrect");
            $(this).addClass("correct");
            $("#connections-tip").removeClass("hidden");
            $("#connections-error").addClass("hidden");
            checkRequired();
        } else {
            $(this).removeClass("correct");
            $(this).addClass("incorrect");
            $("#connections-tip").addClass("hidden");
            $("#connections-error").removeClass("hidden");
            checkRequired();
        }
    });
    
    $("#port").bind('keyup blur',function(){
        if (!this.value || isFinite(this.value)){
            $(this).removeClass("incorrect");
            $(this).addClass("correct");
            $("#port-tip").removeClass("hidden");
            $("#port-error").addClass("hidden");
        } else {
            $(this).removeClass("correct");
            $(this).addClass("incorrect");
            $("#port-tip").addClass("hidden");
            $("#port-error").removeClass("hidden");
        }
    });
    
    $("#host").bind('keyup blur',function(){
        if (this.value){
            $(this).removeClass("incorrect");
            $(this).addClass("correct");
            $("#host-tip").removeClass("hidden");
            $("#host-error").addClass("hidden");
            checkRequired();
        } else {
            $(this).removeClass("correct");
            $(this).addClass("incorrect");
            $("#host-tip").addClass("hidden");
            $("#host-error").removeClass("hidden");
            checkRequired();
        }
    });
});
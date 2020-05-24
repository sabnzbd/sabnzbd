/**
    Base variables and functions
**/
var fadeOnDeleteDuration = 400; // ms after deleting a row
var isMobile = (/android|webos|iphone|ipad|ipod|blackberry|iemobile|opera mini/i.test(navigator.userAgent.toLowerCase()));

// To avoid problems when localStorage is disabled
var hasLocalStorage = true;
function localStorageSetItem(varToSet, valueToSet) { try { return localStorage.setItem(varToSet, valueToSet); } catch(e) { hasLocalStorage = false; } }
function localStorageGetItem(varToGet) { try { return localStorage.getItem(varToGet); } catch(e) {  hasLocalStorage = false; } }

// For mobile we disable zoom while a modal is being opened
// so it will not zoom unnecessarily on the modal
if(isMobile) {
    $('.modal').on('show.bs.modal', function() {
        $('meta[name="viewport"]').attr('content', 'width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no');
    });

    // Restore on modal-close. Need timeout, otherwise it doesn't work
    $('.modal').on('hidden.bs.modal', function() {
        setTimeout(function() {
            $('meta[name="viewport"]').attr('content', 'width=device-width, initial-scale=1');
        },500);
    });
}

// Basic API-call
function callAPI(data) {
    // Fill basis var's
    data.output = "json";
    data.apikey = apiKey;
    var ajaxQuery = $.ajax({
        url: "./api",
        type: "GET",
        cache: false,
        data: data,
        timeout: 10000 // Wait a little longer on mobile connections
    });

    return $.when(ajaxQuery);
}

// Special API call
function callSpecialAPI(url, data) {
    // Did we get input?
    if(data == undefined) data = {};
    // Fill basis var's
    data.output = "json";
    data.apikey = apiKey;
    var ajaxQuery = $.ajax({
        url: url,
        type: "GET",
        cache: false,
        data: data
    });

    return $.when(ajaxQuery);
}

/**
    Handle visibility changes so we
    do only incremental update when not visible
**/
var pageIsVisible = true;
// Set the name of the hidden property and the change event for visibility
var hidden, visibilityChange;
if(typeof document.hidden !== "undefined") { // Opera 12.10 and Firefox 18 and later support
    hidden = "hidden";
    visibilityChange = "visibilitychange";
} else if(typeof document.mozHidden !== "undefined") {
    hidden = "mozHidden";
    visibilityChange = "mozvisibilitychange";
} else if(typeof document.msHidden !== "undefined") {
    hidden = "msHidden";
    visibilityChange = "msvisibilitychange";
} else if(typeof document.webkitHidden !== "undefined") {
    hidden = "webkitHidden";
    visibilityChange = "webkitvisibilitychange";
}

// Set the global visibility
function handleVisibilityChange() {
    if(document[hidden]) {
        pageIsVisible = false;
    } else {
        pageIsVisible = true;
    }
}

// Add event listener only for supported browsers
if(typeof document.addEventListener !== "undefined" && typeof document[hidden] !== "undefined") {
    // Handle page visibility change
    document.addEventListener(visibilityChange, handleVisibilityChange, false);
}

/***
    GENERAL FUNCTIONS
***/
// Function to fix percentages
function fixPercentages(intPercent) {
    // Skip NaN's
    if(isNaN(intPercent))
        intPercent = 0;
    return Math.floor(intPercent || 0) + '%';
}

// Convert HTML tags to regular text
function convertHTMLtoText(htmltxt) {
    return $('<div>').text(htmltxt).html().replace(/&lt;br\/&gt;/g, '<br/>')
}

// Function to re-write 0:09:21=>9:21, 0:10:10=>10:10, 0:00:30=>0:30
function rewriteTime(timeString) {
    // Remove "0:0" from start
    if(timeString.substring(0,3) == '0:0') {
        timeString = timeString.substring(3)
    }
    // Remove "0:" from start
    else if(timeString.substring(0,2) == '0:') {
        timeString = timeString.substring(2)
    }
    return timeString
}

// How to display the date-time?
function displayDateTime(inDate, outFormat, inFormat) {
    // What input?
    if(inDate == '') {
        var theMoment = moment()
    } else {
        var theMoment = moment.utc(inDate, inFormat)
    }
    // Special format or regular format?
    if(outFormat == 'fromNow') {
        return theMoment.fromNow()
    } else {
        return theMoment.local().format(outFormat)
    }
}

// Keep dropdowns open
function keepOpen(thisItem) {
    // Make sure we clicked the a and not the glyphicon/caret!
    if(!$(thisItem).is('a') && !$(thisItem).is('button')) {
        // Do it again on the parent
        keepOpen(thisItem.parentElement)
        return;
    }

    // Onlick so it works for the dynamic items!
    $(thisItem).siblings('.dropdown-menu').children().click(function(e) {
        // Not for links
        if(!$(e.target).is('a')) {
            e.stopPropagation();
        }
    });
    // Add possible tooltips and make sure they get removed
    if(!isMobile)  {
        $(thisItem).siblings('.dropdown-menu').children('[data-tooltip="true"]').tooltip({ trigger: 'hover', container: 'body' })
        $(thisItem).parent().on('hide.bs.dropdown', function() {
            $(thisItem).siblings('.dropdown-menu').children('[data-tooltip="true"]').tooltip('hide')
        })
    }
}

// Show history details
function showDetails(thisItem) {
    // Unfortunatly the .dropdown('toggle') doesn't work in this setup, so work-a-round

    // Open the details of this, or close it?
    if($(thisItem).parent().find('.delete>.dropdown').hasClass('open')) {
        // One click = close
        $(thisItem).parent().find('.delete>.dropdown>a').click()
    } else {
        // Needs timeout, otherwise it thinks its the 'close' click for some reason
        setTimeout(function() {
            $(thisItem).parent().find('.delete>.dropdown>a').click()
        },1)
    }
}

// Check all functionality
function checkAllFiles(objCheck, onlyCheck) {
    // Get which ones we care about
    var allChecks = $($(objCheck).data('checkrange')).filter(':not(:disabled):visible');

    // We need to re-evaltuate the state of this check-all
    // Otherwise the 'inderterminate' will be overwritten by the click event!
    setCheckAllState('#'+objCheck.id, $(objCheck).data('checkrange'))

    // Now we can check what happend
    if(objCheck.indeterminate) {
        // Uncheck if we don't need trigger
        if(onlyCheck) {
            allChecks.filter(":checked").prop('checked', false)
        } else  {
            allChecks.filter(":checked").trigger("click")
        }
    } else {
        // Toggle their state by a click
        allChecks.trigger("click")
    }
}

// To update the check-all button nicely
function setCheckAllState(checkSelector, rangeSelector) {
    // See how many are checked
    var allChecks = $(rangeSelector).filter(':not(:disabled):visible')
    var nrChecks = allChecks.filter(":checked");
    if(nrChecks.length === 0) {
        $(checkSelector).prop({'checked': false, 'indeterminate': false})
    } else if(nrChecks.length == allChecks.length) {
        $(checkSelector).prop({'checked': true, 'indeterminate': false})
    } else {
        $(checkSelector).prop({'checked': false, 'indeterminate': true})
    }
}

// Shift-range functionality for checkboxes
function checkShiftRange(strCheckboxes) {
    // Get them all
    var arrAllChecks = $(strCheckboxes);
    // Get index of the first and last
    var startCheck = arrAllChecks.index($(strCheckboxes + ':checked:first'));
    var endCheck = arrAllChecks.index($(strCheckboxes + ':checked:last'));
    // Everything in between click it to trigger addMultiEdit
    arrAllChecks.slice(startCheck, endCheck).filter(':not(:checked)').trigger('click')
}

// Hide completed files in files-modal
function hideCompletedFiles() {
    if($('#filelist-showcompleted').hasClass('hover-button')) {
        // Hide all
        $('.item-files-table tr.files-done').hide();
        $('#filelist-showcompleted').removeClass('hover-button')
        // Set storage
        localStorageSetItem('showCompletedFiles', 'No')
    } else {
        // show all
        $('.item-files-table tr.files-done').show();
        $('#filelist-showcompleted').addClass('hover-button')
        // Set storage
        localStorageSetItem('showCompletedFiles', 'Yes')
    }
}

// Show status modal and switch to orphaned jobs tab
function showOrphans() {
    $('a[href="#modal-options"]').click().parent().click();
    $('a[href="#options-orphans"]').click()
}

// Show notification
function showNotification(notiName, notiTimeout, fileCounter) {
    // Set uploadcounter if there is one
    $('.main-notification-box .main-notification-box-file-count').text(fileCounter)

    // Hide others, show the new one
    $('.main-notification-box>div').hide()
    $(notiName).css('display', 'inline')
    // Only fade in when hidden
    $('.main-notification-box:hidden').fadeIn()

    // Remove after timeout
    if(notiTimeout) {
        setTimeout(function() {
            hideNotification(true);
        }, notiTimeout)
    }
}

// Hide notification
function hideNotification(fadeItOut) {
    // Hide the box with or without effect
    if(fadeItOut) {
        $('.main-notification-box').fadeOut()
    } else {
        $('.main-notification-box').hide()
    }

}
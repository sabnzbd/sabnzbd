/*
 * jQuery corner plugin
 *
 * version 1.92 (12/18/2007)
 *
 * Dual licensed under the MIT and GPL licenses:
 *   http://www.opensource.org/licenses/mit-license.php
 *   http://www.gnu.org/licenses/gpl.html
 */

/**
 * The corner() method provides a simple way of styling DOM elements.  
 *
 * corner() takes a single string argument:  $().corner("effect corners width")
 *
 *   effect:  The name of the effect to apply, such as round or bevel. 
 *            If you don't specify an effect, rounding is used.
 *
 *   corners: The corners can be one or more of top, bottom, tr, tl, br, or bl. 
 *            By default, all four corners are adorned. 
 *
 *   width:   The width specifies the width of the effect; in the case of rounded corners this 
 *            will be the radius of the width. 
 *            Specify this value using the px suffix such as 10px, and yes it must be pixels.
 *
 * For more details see: http://methvin.com/jquery/jq-corner.html
 * For a full demo see:  http://malsup.com/jquery/corner/
 *
 *
 * @example $('.adorn').corner();
 * @desc Create round, 10px corners 
 *
 * @example $('.adorn').corner("25px");
 * @desc Create round, 25px corners 
 *
 * @example $('.adorn').corner("notch bottom");
 * @desc Create notched, 10px corners on bottom only
 *
 * @example $('.adorn').corner("tr dog 25px");
 * @desc Create dogeared, 25px corner on the top-right corner only
 *
 * @example $('.adorn').corner("round 8px").parent().css('padding', '4px').corner("round 10px");
 * @desc Create a rounded border effect by styling both the element and its parent
 * 
 * @name corner
 * @type jQuery
 * @param String options Options which control the corner style
 * @cat Plugins/Corner
 * @return jQuery
 * @author Dave Methvin (dave.methvin@gmail.com)
 * @author Mike Alsup (malsup@gmail.com)
 */
(function($) { 

$.fn.corner = function(o) {
    var ie6 = $.browser.msie && /MSIE 6.0/.test(navigator.userAgent);
    function sz(el, p) { return parseInt($.css(el,p))||0; };
    function hex2(s) {
        var s = parseInt(s).toString(16);
        return ( s.length < 2 ) ? '0'+s : s;
    };
    function gpc(node) {
        for ( ; node && node.nodeName.toLowerCase() != 'html'; node = node.parentNode ) {
            var v = $.css(node,'backgroundColor');
            if ( v.indexOf('rgb') >= 0 ) { 
                if ($.browser.safari && v == 'rgba(0, 0, 0, 0)')
                    continue;
                var rgb = v.match(/\d+/g); 
                return '#'+ hex2(rgb[0]) + hex2(rgb[1]) + hex2(rgb[2]);
            }
            if ( v && v != 'transparent' )
                return v;
        }
        return '#ffffff';
    };
    function getW(i) {
        switch(fx) {
        case 'round':  return Math.round(width*(1-Math.cos(Math.asin(i/width))));
        case 'cool':   return Math.round(width*(1+Math.cos(Math.asin(i/width))));
        case 'sharp':  return Math.round(width*(1-Math.cos(Math.acos(i/width))));
        case 'bite':   return Math.round(width*(Math.cos(Math.asin((width-i-1)/width))));
        case 'slide':  return Math.round(width*(Math.atan2(i,width/i)));
        case 'jut':    return Math.round(width*(Math.atan2(width,(width-i-1))));
        case 'curl':   return Math.round(width*(Math.atan(i)));
        case 'tear':   return Math.round(width*(Math.cos(i)));
        case 'wicked': return Math.round(width*(Math.tan(i)));
        case 'long':   return Math.round(width*(Math.sqrt(i)));
        case 'sculpt': return Math.round(width*(Math.log((width-i-1),width)));
        case 'dog':    return (i&1) ? (i+1) : width;
        case 'dog2':   return (i&2) ? (i+1) : width;
        case 'dog3':   return (i&3) ? (i+1) : width;
        case 'fray':   return (i%2)*width;
        case 'notch':  return width; 
        case 'bevel':  return i+1;
        }
    };
    o = (o||"").toLowerCase();
    var keep = /keep/.test(o);                       // keep borders?
    var cc = ((o.match(/cc:(#[0-9a-f]+)/)||[])[1]);  // corner color
    var sc = ((o.match(/sc:(#[0-9a-f]+)/)||[])[1]);  // strip color
    var width = parseInt((o.match(/(\d+)px/)||[])[1]) || 10; // corner width
    var re = /round|bevel|notch|bite|cool|sharp|slide|jut|curl|tear|fray|wicked|sculpt|long|dog3|dog2|dog/;
    var fx = ((o.match(re)||['round'])[0]);
    var edges = { T:0, B:1 };
    var opts = {
        TL:  /top|tl/.test(o),       TR:  /top|tr/.test(o),
        BL:  /bottom|bl/.test(o),    BR:  /bottom|br/.test(o)
    };
    if ( !opts.TL && !opts.TR && !opts.BL && !opts.BR )
        opts = { TL:1, TR:1, BL:1, BR:1 };
    var strip = document.createElement('div');
    strip.style.overflow = 'hidden';
    strip.style.height = '1px';
    strip.style.backgroundColor = sc || 'transparent';
    strip.style.borderStyle = 'solid';
    return this.each(function(index){
        var pad = {
            T: parseInt($.css(this,'paddingTop'))||0,     R: parseInt($.css(this,'paddingRight'))||0,
            B: parseInt($.css(this,'paddingBottom'))||0,  L: parseInt($.css(this,'paddingLeft'))||0
        };

        if ($.browser.msie) this.style.zoom = 1; // force 'hasLayout' in IE
        if (!keep) this.style.border = 'none';
        strip.style.borderColor = cc || gpc(this.parentNode);
        var cssHeight = $.curCSS(this, 'height');

        for (var j in edges) {
            var bot = edges[j];
            // only add stips if needed
            if ((bot && (opts.BL || opts.BR)) || (!bot && (opts.TL || opts.TR))) {
                strip.style.borderStyle = 'none '+(opts[j+'R']?'solid':'none')+' none '+(opts[j+'L']?'solid':'none');
                var d = document.createElement('div');
                $(d).addClass('jquery-corner');
                var ds = d.style;

                bot ? this.appendChild(d) : this.insertBefore(d, this.firstChild);

                if (bot && cssHeight != 'auto') {
                    if ($.css(this,'position') == 'static')
                        this.style.position = 'relative';
                    ds.position = 'absolute';
                    ds.bottom = ds.left = ds.padding = ds.margin = '0';
                    if ($.browser.msie)
                        ds.setExpression('width', 'this.parentNode.offsetWidth');
                    else
                        ds.width = '100%';
                }
                else if (!bot && $.browser.msie) {
                    if ($.css(this,'position') == 'static')
                        this.style.position = 'relative';
                    ds.position = 'absolute';
                    ds.top = ds.left = ds.right = ds.padding = ds.margin = '0';
                    
                    // fix ie6 problem when blocked element has a border width
                    var bw = 0;
                    if (ie6 || !$.boxModel)
                        bw = sz(this,'borderLeftWidth') + sz(this,'borderRightWidth');
                    ie6 ? ds.setExpression('width', 'this.parentNode.offsetWidth - '+bw+'+ "px"') : ds.width = '100%';
                }
                else {
                    ds.margin = !bot ? '-'+pad.T+'px -'+pad.R+'px '+(pad.T-width)+'px -'+pad.L+'px' : 
                                        (pad.B-width)+'px -'+pad.R+'px -'+pad.B+'px -'+pad.L+'px';                
                }

                for (var i=0; i < width; i++) {
                    var w = Math.max(0,getW(i));
                    var e = strip.cloneNode(false);
                    e.style.borderWidth = '0 '+(opts[j+'R']?w:0)+'px 0 '+(opts[j+'L']?w:0)+'px';
                    bot ? d.appendChild(e) : d.insertBefore(e, d.firstChild);
                }
            }
        }
    });
};

$.fn.uncorner = function(o) { return $('.jquery-corner', this).remove(); };
    
})(jQuery);

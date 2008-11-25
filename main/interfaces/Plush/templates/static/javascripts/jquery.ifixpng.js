/*
 * jQuery ifixpng plugin
 * (previously known as pngfix)
 * Version 3.1.2  (2008/09/01)
 * @requires jQuery v1.2.6 or above, or a lower version with the dimensions plugin
 * 
 * Based on the plugin by Kush M., http://jquery.khurshid.com
 *
 * Background position Fixed
 * Also fixes non-visible images
 * (c) Copyright Yereth Jansen (yereth@yereth.nl)
 * personal website: http://www.yereth.nl
 * Company website: http://www.wharf.nl
 * 
 * Dual licensed under the MIT and GPL licenses:
 * http://www.opensource.org/licenses/mit-license.php
 * http://www.gnu.org/licenses/gpl.html
 *
 * For a demonstration of the background-position being fixed:
 * http://www.yereth.nl/bgpos.html
 *
 * Plugin page:
 * http://plugins.jquery.com/project/iFixPng2
 *
 */

/**
 *
 * @example
 *
 * optional if location of pixel.gif if different to default which is images/pixel.gif
 * $.ifixpng('media/pixel.gif');
 *
 * $('img[@src$=.png], #panel').ifixpng();
 *
 * @apply hack to all png images and #panel which icluded png img in its css
 *
 * @name ifixpng
 * @type jQuery
 * @cat Plugins/Image
 * @return jQuery
 * @author jQuery Community
 */
;(function($) {

	/**
	 * helper variables and function
	 */
	$.ifixpng = function(customPixel) {
		$.ifixpng.pixel = customPixel;
	};
	
	$.ifixpng.regexp = {
		bg: /^url\(["']?(.*\.png([?].*)?)["']?\)$/i,
		img: /.*\.png([?].*)?$/i
	},
	
	$.ifixpng.getPixel = function() {
		return $.ifixpng.pixel || 'images/pixel.gif';
	};
	
	var hack = {
		base	: $('base').attr('href'),
		ltie7	: $.browser.msie && $.browser.version < 7,
		filter	: function(src) {
			return "progid:DXImageTransform.Microsoft.AlphaImageLoader(enabled=true,sizingMethod=crop,src='"+src+"')";
		}
	};
	
	/**
	 * Applies ie png hack to selected dom elements
	 *
	 * $('img[@src$=.png]').ifixpng();
	 * @desc apply hack to all images with png extensions
	 *
	 * $('#panel, img[@src$=.png]').ifixpng();
	 * @desc apply hack to element #panel and all images with png extensions
	 *
	 * @name ifixpng
	 */
	 
	$.fn.ifixpng = hack.ltie7 ? function() {
		function fixImage(image, source, width, height, hidden) {
			image.css({filter:hack.filter(source), width: width, height: height})
			  .attr({src:$.ifixpng.getPixel()})
			  .positionFix();
		}
		
    	return this.each(function() {
			var $$ = $(this);
			if ($$.is('img') || $$.is('input')) { // hack image tags present in dom
				var source, img;
				if (this.src && this.src.match($.ifixpng.regexp.img)) { // make sure it is png image
					// use source tag value if set 
					source = (hack.base && this.src.substring(0,1)!='/' && this.src.indexOf(hack.base) === -1) ? hack.base + this.src : this.src;
					// If the width is not set, we have a problem; the image is not probably visible or not loaded
					// and we need a work around.
					if (!this.width || !this.height) {
						$(new Image()).one('load', function() {
							fixImage($$, source, this.width, this.height);
							$(this).remove();
						}).attr('src', source);
					// If the image already has dimensions (it's loaded and visible) we can fix it straight away.
					} else fixImage($$, source, this.width, this.height);
				}
			} else if (this.style) { // hack png css properties present inside css
				var imageSrc = $$.css('backgroundImage');
				// Background repeated images we cannot fix unfortunately
				if (imageSrc && imageSrc.match($.ifixpng.regexp.bg) && this.currentStyle.backgroundRepeat == 'no-repeat') {
					imageSrc = RegExp.$1;
					var x = this.currentStyle.backgroundPositionX || 0, y = this.currentStyle.backgroundPositionY || 0;
					if (x || y) {
						var css = {}, img;
						if (typeof x != 'undefined') {
							if (x == 'left') css.left = 0; 
							// if right is 0, we have to check if the parent has an odd width, because of an IE bug
							else if (x == 'right') css.right = $$.width() % 2 === 1 ? -1 : 0;
							else css.left = x;
						}
						if (typeof y != 'undefined') {
							// if bottom is 0, we have to check if the parent has an odd height, because of an IE bug
							if (y == 'bottom') css.bottom = $$.height() % 2 === 1 ? -1 : 0; 
							else if (y == 'top') css.top = 0;
							else css.top = y;
						}
						img = new Image();
						$(img).one('load', function() {
							var x,y, expr = {}, prop;
							// Now the image is loaded for sure, we can see if the background position needs fixing with an expression (in case of percentages)
							if (/center|%/.test(css.top)) {
								expr.top = "(this.parentNode.offsetHeight - this.offsetHeight) * " + (css.top == 'center' ? 0.5 : (parseInt(css.top) / 100));
								delete css.top;
							}
							if (/center|%/.test(css.left)) {
								expr.left = "(this.parentNode.offsetWidth - this.offsetWidth) * " + (css.left == 'center' ? 0.5 : (parseInt(css.left) / 100));
								delete css.left;
							}
							// Let's add the helper DIV which will simulate the background image
							$$.positionFix().css({backgroundImage: 'none'}).prepend(
								$('<div></div>').css(css).css({
									width: this.width,
									height: this.height,
									position: 'absolute',
									filter: hack.filter(imageSrc)
								})
							);
							if (expr.top || expr.left) {
								var elem = $$.children(':first')[0];
								for (prop in expr) elem.style.setExpression(prop, expr[prop], 'JavaScript');
							}
							$(this).remove();
						});
						img.src = imageSrc;
					} else {
						$$.css({backgroundImage: 'none', filter:hack.filter(imageSrc)});
					}
				}
			}
		});
	} : function() { return this; };
	
	/**
	 * positions selected item relatively
	 */
	$.fn.positionFix = function() {
		return this.each(function() {
			var $$ = $(this);
			if ($$.css('position') != 'absolute') $$.css({position:'relative'});
		});
	};

})(jQuery);
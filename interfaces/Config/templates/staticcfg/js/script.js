/* =============================================================
 * bootstrap3-typeahead.js v4.0.2
 * https://github.com/bassjobsen/Bootstrap-3-Typeahead
 * =============================================================
 * Original written by @mdo and @fat
 * =============================================================
 * Copyright 2014 Bass Jobsen @bassjobsen
 *
 * Licensed under the Apache License, Version 2.0 (the 'License');
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an 'AS IS' BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 * ============================================================ */
 (function(root,factory){"use strict";if(typeof module!=="undefined"&&module.exports){module.exports=factory(require("jquery"))}else if(typeof define==="function"&&define.amd){define(["jquery"],function($){return factory($)})}else{factory(root.jQuery)}})(this,function($){"use strict";var Typeahead=function(element,options){this.$element=$(element);this.options=$.extend({},$.fn.typeahead.defaults,options);this.matcher=this.options.matcher||this.matcher;this.sorter=this.options.sorter||this.sorter;this.select=this.options.select||this.select;this.autoSelect=typeof this.options.autoSelect=="boolean"?this.options.autoSelect:true;this.highlighter=this.options.highlighter||this.highlighter;this.render=this.options.render||this.render;this.updater=this.options.updater||this.updater;this.displayText=this.options.displayText||this.displayText;this.source=this.options.source;this.delay=this.options.delay;this.$menu=$(this.options.menu);this.$appendTo=this.options.appendTo?$(this.options.appendTo):null;this.fitToElement=typeof this.options.fitToElement=="boolean"?this.options.fitToElement:false;this.shown=false;this.listen();this.showHintOnFocus=typeof this.options.showHintOnFocus=="boolean"||this.options.showHintOnFocus==="all"?this.options.showHintOnFocus:false;this.afterSelect=this.options.afterSelect;this.addItem=false;this.value=this.$element.val()||this.$element.text()};Typeahead.prototype={constructor:Typeahead,select:function(){var val=this.$menu.find(".active").data("value");this.$element.data("active",val);if(this.autoSelect||val){var newVal=this.updater(val);if(!newVal){newVal=""}this.$element.val(this.displayText(newVal)||newVal).text(this.displayText(newVal)||newVal).change();this.afterSelect(newVal)}return this.hide()},updater:function(item){return item},setSource:function(source){this.source=source},show:function(){var pos=$.extend({},this.$element.position(),{height:this.$element[0].offsetHeight});var scrollHeight=typeof this.options.scrollHeight=="function"?this.options.scrollHeight.call():this.options.scrollHeight;var element;if(this.shown){element=this.$menu}else if(this.$appendTo){element=this.$menu.appendTo(this.$appendTo);this.hasSameParent=this.$appendTo.is(this.$element.parent())}else{element=this.$menu.insertAfter(this.$element);this.hasSameParent=true}if(!this.hasSameParent){element.css("position","fixed");var offset=this.$element.offset();pos.top=offset.top;pos.left=offset.left}var dropup=$(element).parent().hasClass("dropup");var newTop=dropup?"auto":pos.top+pos.height+scrollHeight;var right=$(element).hasClass("dropdown-menu-right");var newLeft=right?"auto":pos.left;element.css({top:newTop,left:newLeft}).show();if(this.options.fitToElement===true){element.css("width",this.$element.outerWidth()+"px")}this.shown=true;return this},hide:function(){this.$menu.hide();this.shown=false;return this},lookup:function(query){var items;if(typeof query!="undefined"&&query!==null){this.query=query}else{this.query=this.$element.val()||this.$element.text()||""}if(this.query.length<this.options.minLength&&!this.options.showHintOnFocus){return this.shown?this.hide():this}var worker=$.proxy(function(){if($.isFunction(this.source)){this.source(this.query,$.proxy(this.process,this))}else if(this.source){this.process(this.source)}},this);clearTimeout(this.lookupWorker);this.lookupWorker=setTimeout(worker,this.delay)},process:function(items){var that=this;items=$.grep(items,function(item){return that.matcher(item)});items=this.sorter(items);if(!items.length&&!this.options.addItem){return this.shown?this.hide():this}if(items.length>0){this.$element.data("active",items[0])}else{this.$element.data("active",null)}if(this.options.addItem){items.push(this.options.addItem)}if(this.options.items=="all"){return this.render(items).show()}else{return this.render(items.slice(0,this.options.items)).show()}},matcher:function(item){var it=this.displayText(item);return~it.toLowerCase().indexOf(this.query.toLowerCase())},sorter:function(items){var beginswith=[];var caseSensitive=[];var caseInsensitive=[];var item;while(item=items.shift()){var it=this.displayText(item);if(!it.toLowerCase().indexOf(this.query.toLowerCase()))beginswith.push(item);else if(~it.indexOf(this.query))caseSensitive.push(item);else caseInsensitive.push(item)}return beginswith.concat(caseSensitive,caseInsensitive)},highlighter:function(item){var html=$("<div></div>");var query=this.query;var i=item.toLowerCase().indexOf(query.toLowerCase());var len=query.length;var leftPart;var middlePart;var rightPart;var strong;if(len===0){return html.text(item).html()}while(i>-1){leftPart=item.substr(0,i);middlePart=item.substr(i,len);rightPart=item.substr(i+len);strong=$("<strong></strong>").text(middlePart);html.append(document.createTextNode(leftPart)).append(strong);item=rightPart;i=item.toLowerCase().indexOf(query.toLowerCase())}return html.append(document.createTextNode(item)).html()},render:function(items){var that=this;var self=this;var activeFound=false;var data=[];var _category=that.options.separator;$.each(items,function(key,value){if(key>0&&value[_category]!==items[key-1][_category]){data.push({__type:"divider"})}if(value[_category]&&(key===0||value[_category]!==items[key-1][_category])){data.push({__type:"category",name:value[_category]})}data.push(value)});items=$(data).map(function(i,item){if((item.__type||false)=="category"){return $(that.options.headerHtml).text(item.name)[0]}if((item.__type||false)=="divider"){return $(that.options.headerDivider)[0]}var text=self.displayText(item);i=$(that.options.item).data("value",item);i.find("a").html(that.highlighter(text,item));if(text==self.$element.val()){i.addClass("active");self.$element.data("active",item);activeFound=true}return i[0]});if(this.autoSelect&&!activeFound){items.filter(":not(.dropdown-header)").first().addClass("active");this.$element.data("active",items.first().data("value"))}this.$menu.html(items);return this},displayText:function(item){return typeof item!=="undefined"&&typeof item.name!="undefined"&&item.name||item},next:function(event){var active=this.$menu.find(".active").removeClass("active");var next=active.next();if(!next.length){next=$(this.$menu.find("li")[0])}next.addClass("active")},prev:function(event){var active=this.$menu.find(".active").removeClass("active");var prev=active.prev();if(!prev.length){prev=this.$menu.find("li").last()}prev.addClass("active")},listen:function(){this.$element.on("focus",$.proxy(this.focus,this)).on("blur",$.proxy(this.blur,this)).on("keypress",$.proxy(this.keypress,this)).on("input",$.proxy(this.input,this)).on("keyup",$.proxy(this.keyup,this));if(this.eventSupported("keydown")){this.$element.on("keydown",$.proxy(this.keydown,this))}this.$menu.on("click",$.proxy(this.click,this)).on("mouseenter","li",$.proxy(this.mouseenter,this)).on("mouseleave","li",$.proxy(this.mouseleave,this)).on("mousedown",$.proxy(this.mousedown,this))},destroy:function(){this.$element.data("typeahead",null);this.$element.data("active",null);this.$element.off("focus").off("blur").off("keypress").off("input").off("keyup");if(this.eventSupported("keydown")){this.$element.off("keydown")}this.$menu.remove();this.destroyed=true},eventSupported:function(eventName){var isSupported=eventName in this.$element;if(!isSupported){this.$element.setAttribute(eventName,"return;");isSupported=typeof this.$element[eventName]==="function"}return isSupported},move:function(e){if(!this.shown)return;switch(e.keyCode){case 9:case 13:case 27:e.preventDefault();break;case 38:if(e.shiftKey)return;e.preventDefault();this.prev();break;case 40:if(e.shiftKey)return;e.preventDefault();this.next();break}},keydown:function(e){this.suppressKeyPressRepeat=~$.inArray(e.keyCode,[40,38,9,13,27]);if(!this.shown&&e.keyCode==40){this.lookup()}else{this.move(e)}},keypress:function(e){if(this.suppressKeyPressRepeat)return;this.move(e)},input:function(e){var currentValue=this.$element.val()||this.$element.text();if(this.value!==currentValue){this.value=currentValue;this.lookup()}},keyup:function(e){if(this.destroyed){return}switch(e.keyCode){case 40:case 38:case 16:case 17:case 18:break;case 9:case 13:if(!this.shown)return;this.select();break;case 27:if(!this.shown)return;this.hide();break}},focus:function(e){if(!this.focused){this.focused=true;if(this.options.showHintOnFocus&&this.skipShowHintOnFocus!==true){if(this.options.showHintOnFocus==="all"){this.lookup("")}else{this.lookup()}}}if(this.skipShowHintOnFocus){this.skipShowHintOnFocus=false}},blur:function(e){if(!this.mousedover&&!this.mouseddown&&this.shown){this.hide();this.focused=false}else if(this.mouseddown){this.skipShowHintOnFocus=true;this.$element.focus();this.mouseddown=false}},click:function(e){e.preventDefault();this.skipShowHintOnFocus=true;this.select();this.$element.focus();this.hide()},mouseenter:function(e){this.mousedover=true;this.$menu.find(".active").removeClass("active");$(e.currentTarget).addClass("active")},mouseleave:function(e){this.mousedover=false;if(!this.focused&&this.shown)this.hide()},mousedown:function(e){this.mouseddown=true;this.$menu.one("mouseup",function(e){this.mouseddown=false}.bind(this))}};var old=$.fn.typeahead;$.fn.typeahead=function(option){var arg=arguments;if(typeof option=="string"&&option=="getActive"){return this.data("active")}return this.each(function(){var $this=$(this);var data=$this.data("typeahead");var options=typeof option=="object"&&option;if(!data)$this.data("typeahead",data=new Typeahead(this,options));if(typeof option=="string"&&data[option]){if(arg.length>1){data[option].apply(data,Array.prototype.slice.call(arg,1))}else{data[option]()}}})};$.fn.typeahead.defaults={source:[],items:8,menu:'<ul class="typeahead dropdown-menu" role="listbox"></ul>',item:'<li><a class="dropdown-item" href="#" role="option"></a></li>',minLength:1,scrollHeight:0,autoSelect:true,afterSelect:$.noop,addItem:false,delay:0,separator:"category",headerHtml:'<li class="dropdown-header"></li>',headerDivider:'<li class="divider" role="separator"></li>'};$.fn.typeahead.Constructor=Typeahead;$.fn.typeahead.noConflict=function(){$.fn.typeahead=old;return this};$(document).on("focus.typeahead.data-api",'[data-provide="typeahead"]',function(e){var $this=$(this);if($this.data("typeahead"))return;$this.typeahead($this.data())})});
/*!
  * jQuery Form Plugin
  * version: 4.2.2
  * Requires jQuery v1.7.2 or later
  * Project repository: https://github.com/jquery-form/form

  * Copyright 2017 Kevin Morris
  * Copyright 2006 M. Alsup

  * Dual licensed under the LGPL-2.1+ or MIT licenses
  * https://github.com/jquery-form/form#license

  * This library is free software; you can redistribute it and/or
  * modify it under the terms of the GNU Lesser General Public
  * License as published by the Free Software Foundation; either
  * version 2.1 of the License, or (at your option) any later version.
  * This library is distributed in the hope that it will be useful,
  * but WITHOUT ANY WARRANTY; without even the implied warranty of
  * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
  * Lesser General Public License for more details.
  */
 !function(e){"function"==typeof define&&define.amd?define(["jquery"],e):"object"==typeof module&&module.exports?module.exports=function(t,r){return void 0===r&&(r="undefined"!=typeof window?require("jquery"):require("jquery")(t)),e(r),r}:e(jQuery)}(function(e){"use strict";function t(t){var r=t.data;t.isDefaultPrevented()||(t.preventDefault(),e(t.target).closest("form").ajaxSubmit(r))}function r(t){var r=t.target,a=e(r);if(!a.is("[type=submit],[type=image]")){var n=a.closest("[type=submit]");if(0===n.length)return;r=n[0]}var i=r.form;if(i.clk=r,"image"===r.type)if(void 0!==t.offsetX)i.clk_x=t.offsetX,i.clk_y=t.offsetY;else if("function"==typeof e.fn.offset){var o=a.offset();i.clk_x=t.pageX-o.left,i.clk_y=t.pageY-o.top}else i.clk_x=t.pageX-r.offsetLeft,i.clk_y=t.pageY-r.offsetTop;setTimeout(function(){i.clk=i.clk_x=i.clk_y=null},100)}function a(){if(e.fn.ajaxSubmit.debug){var t="[jquery.form] "+Array.prototype.join.call(arguments,"");window.console&&window.console.log?window.console.log(t):window.opera&&window.opera.postError&&window.opera.postError(t)}}var n=/\r?\n/g,i={};i.fileapi=void 0!==e('<input type="file">').get(0).files,i.formdata=void 0!==window.FormData;var o=!!e.fn.prop;e.fn.attr2=function(){if(!o)return this.attr.apply(this,arguments);var e=this.prop.apply(this,arguments);return e&&e.jquery||"string"==typeof e?e:this.attr.apply(this,arguments)},e.fn.ajaxSubmit=function(t,r,n,s){function u(r){var a,n,i=e.param(r,t.traditional).split("&"),o=i.length,s=[];for(a=0;a<o;a++)i[a]=i[a].replace(/\+/g," "),n=i[a].split("="),s.push([decodeURIComponent(n[0]),decodeURIComponent(n[1])]);return s}function c(r){function n(e){var t=null;try{e.contentWindow&&(t=e.contentWindow.document)}catch(e){a("cannot get iframe.contentWindow document: "+e)}if(t)return t;try{t=e.contentDocument?e.contentDocument:e.document}catch(r){a("cannot get iframe.contentDocument: "+r),t=e.document}return t}function i(){function t(){try{var e=n(v).readyState;a("state = "+e),e&&"uninitialized"===e.toLowerCase()&&setTimeout(t,50)}catch(e){a("Server abort: ",e," (",e.name,")"),s(L),j&&clearTimeout(j),j=void 0}}var r=p.attr2("target"),i=p.attr2("action"),o=p.attr("enctype")||p.attr("encoding")||"multipart/form-data";w.setAttribute("target",m),l&&!/post/i.test(l)||w.setAttribute("method","POST"),i!==f.url&&w.setAttribute("action",f.url),f.skipEncodingOverride||l&&!/post/i.test(l)||p.attr({encoding:"multipart/form-data",enctype:"multipart/form-data"}),f.timeout&&(j=setTimeout(function(){T=!0,s(A)},f.timeout));var u=[];try{if(f.extraData)for(var c in f.extraData)f.extraData.hasOwnProperty(c)&&(e.isPlainObject(f.extraData[c])&&f.extraData[c].hasOwnProperty("name")&&f.extraData[c].hasOwnProperty("value")?u.push(e('<input type="hidden" name="'+f.extraData[c].name+'">',k).val(f.extraData[c].value).appendTo(w)[0]):u.push(e('<input type="hidden" name="'+c+'">',k).val(f.extraData[c]).appendTo(w)[0]));f.iframeTarget||h.appendTo(D),v.attachEvent?v.attachEvent("onload",s):v.addEventListener("load",s,!1),setTimeout(t,15);try{w.submit()}catch(e){document.createElement("form").submit.apply(w)}}finally{w.setAttribute("action",i),w.setAttribute("enctype",o),r?w.setAttribute("target",r):p.removeAttr("target"),e(u).remove()}}function s(t){if(!x.aborted&&!X){if((O=n(v))||(a("cannot access response document"),t=L),t===A&&x)return x.abort("timeout"),void S.reject(x,"timeout");if(t===L&&x)return x.abort("server abort"),void S.reject(x,"error","server abort");if(O&&O.location.href!==f.iframeSrc||T){v.detachEvent?v.detachEvent("onload",s):v.removeEventListener("load",s,!1);var r,i="success";try{if(T)throw"timeout";var o="xml"===f.dataType||O.XMLDocument||e.isXMLDoc(O);if(a("isXml="+o),!o&&window.opera&&(null===O.body||!O.body.innerHTML)&&--C)return a("requeing onLoad callback, DOM not available"),void setTimeout(s,250);var u=O.body?O.body:O.documentElement;x.responseText=u?u.innerHTML:null,x.responseXML=O.XMLDocument?O.XMLDocument:O,o&&(f.dataType="xml"),x.getResponseHeader=function(e){return{"content-type":f.dataType}[e.toLowerCase()]},u&&(x.status=Number(u.getAttribute("status"))||x.status,x.statusText=u.getAttribute("statusText")||x.statusText);var c=(f.dataType||"").toLowerCase(),l=/(json|script|text)/.test(c);if(l||f.textarea){var p=O.getElementsByTagName("textarea")[0];if(p)x.responseText=p.value,x.status=Number(p.getAttribute("status"))||x.status,x.statusText=p.getAttribute("statusText")||x.statusText;else if(l){var m=O.getElementsByTagName("pre")[0],g=O.getElementsByTagName("body")[0];m?x.responseText=m.textContent?m.textContent:m.innerText:g&&(x.responseText=g.textContent?g.textContent:g.innerText)}}else"xml"===c&&!x.responseXML&&x.responseText&&(x.responseXML=q(x.responseText));try{M=N(x,c,f)}catch(e){i="parsererror",x.error=r=e||i}}catch(e){a("error caught: ",e),i="error",x.error=r=e||i}x.aborted&&(a("upload aborted"),i=null),x.status&&(i=x.status>=200&&x.status<300||304===x.status?"success":"error"),"success"===i?(f.success&&f.success.call(f.context,M,"success",x),S.resolve(x.responseText,"success",x),d&&e.event.trigger("ajaxSuccess",[x,f])):i&&(void 0===r&&(r=x.statusText),f.error&&f.error.call(f.context,x,i,r),S.reject(x,"error",r),d&&e.event.trigger("ajaxError",[x,f,r])),d&&e.event.trigger("ajaxComplete",[x,f]),d&&!--e.active&&e.event.trigger("ajaxStop"),f.complete&&f.complete.call(f.context,x,i),X=!0,f.timeout&&clearTimeout(j),setTimeout(function(){f.iframeTarget?h.attr("src",f.iframeSrc):h.remove(),x.responseXML=null},100)}}}var u,c,f,d,m,h,v,x,y,b,T,j,w=p[0],S=e.Deferred();if(S.abort=function(e){x.abort(e)},r)for(c=0;c<g.length;c++)u=e(g[c]),o?u.prop("disabled",!1):u.removeAttr("disabled");(f=e.extend(!0,{},e.ajaxSettings,t)).context=f.context||f,m="jqFormIO"+(new Date).getTime();var k=w.ownerDocument,D=p.closest("body");if(f.iframeTarget?(b=(h=e(f.iframeTarget,k)).attr2("name"))?m=b:h.attr2("name",m):(h=e('<iframe name="'+m+'" src="'+f.iframeSrc+'" />',k)).css({position:"absolute",top:"-1000px",left:"-1000px"}),v=h[0],x={aborted:0,responseText:null,responseXML:null,status:0,statusText:"n/a",getAllResponseHeaders:function(){},getResponseHeader:function(){},setRequestHeader:function(){},abort:function(t){var r="timeout"===t?"timeout":"aborted";a("aborting upload... "+r),this.aborted=1;try{v.contentWindow.document.execCommand&&v.contentWindow.document.execCommand("Stop")}catch(e){}h.attr("src",f.iframeSrc),x.error=r,f.error&&f.error.call(f.context,x,r,t),d&&e.event.trigger("ajaxError",[x,f,r]),f.complete&&f.complete.call(f.context,x,r)}},(d=f.global)&&0==e.active++&&e.event.trigger("ajaxStart"),d&&e.event.trigger("ajaxSend",[x,f]),f.beforeSend&&!1===f.beforeSend.call(f.context,x,f))return f.global&&e.active--,S.reject(),S;if(x.aborted)return S.reject(),S;(y=w.clk)&&(b=y.name)&&!y.disabled&&(f.extraData=f.extraData||{},f.extraData[b]=y.value,"image"===y.type&&(f.extraData[b+".x"]=w.clk_x,f.extraData[b+".y"]=w.clk_y));var A=1,L=2,F=e("meta[name=csrf-token]").attr("content"),E=e("meta[name=csrf-param]").attr("content");E&&F&&(f.extraData=f.extraData||{},f.extraData[E]=F),f.forceSync?i():setTimeout(i,10);var M,O,X,C=50,q=e.parseXML||function(e,t){return window.ActiveXObject?((t=new ActiveXObject("Microsoft.XMLDOM")).async="false",t.loadXML(e)):t=(new DOMParser).parseFromString(e,"text/xml"),t&&t.documentElement&&"parsererror"!==t.documentElement.nodeName?t:null},_=e.parseJSON||function(e){return window.eval("("+e+")")},N=function(t,r,a){var n=t.getResponseHeader("content-type")||"",i=("xml"===r||!r)&&n.indexOf("xml")>=0,o=i?t.responseXML:t.responseText;return i&&"parsererror"===o.documentElement.nodeName&&e.error&&e.error("parsererror"),a&&a.dataFilter&&(o=a.dataFilter(o,r)),"string"==typeof o&&(("json"===r||!r)&&n.indexOf("json")>=0?o=_(o):("script"===r||!r)&&n.indexOf("javascript")>=0&&e.globalEval(o)),o};return S}if(!this.length)return a("ajaxSubmit: skipping submit process - no element selected"),this;var l,f,d,p=this;"function"==typeof t?t={success:t}:"string"==typeof t||!1===t&&arguments.length>0?(t={url:t,data:r,dataType:n},"function"==typeof s&&(t.success=s)):void 0===t&&(t={}),l=t.method||t.type||this.attr2("method"),(d=(d="string"==typeof(f=t.url||this.attr2("action"))?e.trim(f):"")||window.location.href||"")&&(d=(d.match(/^([^#]+)/)||[])[1]),t=e.extend(!0,{url:d,success:e.ajaxSettings.success,type:l||e.ajaxSettings.type,iframeSrc:/^https/i.test(window.location.href||"")?"javascript:false":"about:blank"},t);var m={};if(this.trigger("form-pre-serialize",[this,t,m]),m.veto)return a("ajaxSubmit: submit vetoed via form-pre-serialize trigger"),this;if(t.beforeSerialize&&!1===t.beforeSerialize(this,t))return a("ajaxSubmit: submit aborted via beforeSerialize callback"),this;var h=t.traditional;void 0===h&&(h=e.ajaxSettings.traditional);var v,g=[],x=this.formToArray(t.semantic,g,t.filtering);if(t.data){var y=e.isFunction(t.data)?t.data(x):t.data;t.extraData=y,v=e.param(y,h)}if(t.beforeSubmit&&!1===t.beforeSubmit(x,this,t))return a("ajaxSubmit: submit aborted via beforeSubmit callback"),this;if(this.trigger("form-submit-validate",[x,this,t,m]),m.veto)return a("ajaxSubmit: submit vetoed via form-submit-validate trigger"),this;var b=e.param(x,h);v&&(b=b?b+"&"+v:v),"GET"===t.type.toUpperCase()?(t.url+=(t.url.indexOf("?")>=0?"&":"?")+b,t.data=null):t.data=b;var T=[];if(t.resetForm&&T.push(function(){p.resetForm()}),t.clearForm&&T.push(function(){p.clearForm(t.includeHidden)}),!t.dataType&&t.target){var j=t.success||function(){};T.push(function(r,a,n){var i=arguments,o=t.replaceTarget?"replaceWith":"html";e(t.target)[o](r).each(function(){j.apply(this,i)})})}else t.success&&(e.isArray(t.success)?e.merge(T,t.success):T.push(t.success));if(t.success=function(e,r,a){for(var n=t.context||this,i=0,o=T.length;i<o;i++)T[i].apply(n,[e,r,a||p,p])},t.error){var w=t.error;t.error=function(e,r,a){var n=t.context||this;w.apply(n,[e,r,a,p])}}if(t.complete){var S=t.complete;t.complete=function(e,r){var a=t.context||this;S.apply(a,[e,r,p])}}var k=e("input[type=file]:enabled",this).filter(function(){return""!==e(this).val()}).length>0,D="multipart/form-data",A=p.attr("enctype")===D||p.attr("encoding")===D,L=i.fileapi&&i.formdata;a("fileAPI :"+L);var F,E=(k||A)&&!L;!1!==t.iframe&&(t.iframe||E)?t.closeKeepAlive?e.get(t.closeKeepAlive,function(){F=c(x)}):F=c(x):F=(k||A)&&L?function(r){for(var a=new FormData,n=0;n<r.length;n++)a.append(r[n].name,r[n].value);if(t.extraData){var i=u(t.extraData);for(n=0;n<i.length;n++)i[n]&&a.append(i[n][0],i[n][1])}t.data=null;var o=e.extend(!0,{},e.ajaxSettings,t,{contentType:!1,processData:!1,cache:!1,type:l||"POST"});t.uploadProgress&&(o.xhr=function(){var r=e.ajaxSettings.xhr();return r.upload&&r.upload.addEventListener("progress",function(e){var r=0,a=e.loaded||e.position,n=e.total;e.lengthComputable&&(r=Math.ceil(a/n*100)),t.uploadProgress(e,a,n,r)},!1),r}),o.data=null;var s=o.beforeSend;return o.beforeSend=function(e,r){t.formData?r.data=t.formData:r.data=a,s&&s.call(this,e,r)},e.ajax(o)}(x):e.ajax(t),p.removeData("jqxhr").data("jqxhr",F);for(var M=0;M<g.length;M++)g[M]=null;return this.trigger("form-submit-notify",[this,t]),this},e.fn.ajaxForm=function(n,i,o,s){if(("string"==typeof n||!1===n&&arguments.length>0)&&(n={url:n,data:i,dataType:o},"function"==typeof s&&(n.success=s)),n=n||{},n.delegation=n.delegation&&e.isFunction(e.fn.on),!n.delegation&&0===this.length){var u={s:this.selector,c:this.context};return!e.isReady&&u.s?(a("DOM not ready, queuing ajaxForm"),e(function(){e(u.s,u.c).ajaxForm(n)}),this):(a("terminating; zero elements found by selector"+(e.isReady?"":" (DOM not ready)")),this)}return n.delegation?(e(document).off("submit.form-plugin",this.selector,t).off("click.form-plugin",this.selector,r).on("submit.form-plugin",this.selector,n,t).on("click.form-plugin",this.selector,n,r),this):this.ajaxFormUnbind().on("submit.form-plugin",n,t).on("click.form-plugin",n,r)},e.fn.ajaxFormUnbind=function(){return this.off("submit.form-plugin click.form-plugin")},e.fn.formToArray=function(t,r,a){var n=[];if(0===this.length)return n;var o,s=this[0],u=this.attr("id"),c=t||void 0===s.elements?s.getElementsByTagName("*"):s.elements;if(c&&(c=e.makeArray(c)),u&&(t||/(Edge|Trident)\//.test(navigator.userAgent))&&(o=e(':input[form="'+u+'"]').get()).length&&(c=(c||[]).concat(o)),!c||!c.length)return n;e.isFunction(a)&&(c=e.map(c,a));var l,f,d,p,m,h,v;for(l=0,h=c.length;l<h;l++)if(m=c[l],(d=m.name)&&!m.disabled)if(t&&s.clk&&"image"===m.type)s.clk===m&&(n.push({name:d,value:e(m).val(),type:m.type}),n.push({name:d+".x",value:s.clk_x},{name:d+".y",value:s.clk_y}));else if((p=e.fieldValue(m,!0))&&p.constructor===Array)for(r&&r.push(m),f=0,v=p.length;f<v;f++)n.push({name:d,value:p[f]});else if(i.fileapi&&"file"===m.type){r&&r.push(m);var g=m.files;if(g.length)for(f=0;f<g.length;f++)n.push({name:d,value:g[f],type:m.type});else n.push({name:d,value:"",type:m.type})}else null!==p&&void 0!==p&&(r&&r.push(m),n.push({name:d,value:p,type:m.type,required:m.required}));if(!t&&s.clk){var x=e(s.clk),y=x[0];(d=y.name)&&!y.disabled&&"image"===y.type&&(n.push({name:d,value:x.val()}),n.push({name:d+".x",value:s.clk_x},{name:d+".y",value:s.clk_y}))}return n},e.fn.formSerialize=function(t){return e.param(this.formToArray(t))},e.fn.fieldSerialize=function(t){var r=[];return this.each(function(){var a=this.name;if(a){var n=e.fieldValue(this,t);if(n&&n.constructor===Array)for(var i=0,o=n.length;i<o;i++)r.push({name:a,value:n[i]});else null!==n&&void 0!==n&&r.push({name:this.name,value:n})}}),e.param(r)},e.fn.fieldValue=function(t){for(var r=[],a=0,n=this.length;a<n;a++){var i=this[a],o=e.fieldValue(i,t);null===o||void 0===o||o.constructor===Array&&!o.length||(o.constructor===Array?e.merge(r,o):r.push(o))}return r},e.fieldValue=function(t,r){var a=t.name,i=t.type,o=t.tagName.toLowerCase();if(void 0===r&&(r=!0),r&&(!a||t.disabled||"reset"===i||"button"===i||("checkbox"===i||"radio"===i)&&!t.checked||("submit"===i||"image"===i)&&t.form&&t.form.clk!==t||"select"===o&&-1===t.selectedIndex))return null;if("select"===o){var s=t.selectedIndex;if(s<0)return null;for(var u=[],c=t.options,l="select-one"===i,f=l?s+1:c.length,d=l?s:0;d<f;d++){var p=c[d];if(p.selected&&!p.disabled){var m=p.value;if(m||(m=p.attributes&&p.attributes.value&&!p.attributes.value.specified?p.text:p.value),l)return m;u.push(m)}}return u}return e(t).val().replace(n,"\r\n")},e.fn.clearForm=function(t){return this.each(function(){e("input,select,textarea",this).clearFields(t)})},e.fn.clearFields=e.fn.clearInputs=function(t){var r=/^(?:color|date|datetime|email|month|number|password|range|search|tel|text|time|url|week)$/i;return this.each(function(){var a=this.type,n=this.tagName.toLowerCase();r.test(a)||"textarea"===n?this.value="":"checkbox"===a||"radio"===a?this.checked=!1:"select"===n?this.selectedIndex=-1:"file"===a?/MSIE/.test(navigator.userAgent)?e(this).replaceWith(e(this).clone(!0)):e(this).val(""):t&&(!0===t&&/hidden/.test(a)||"string"==typeof t&&e(this).is(t))&&(this.value="")})},e.fn.resetForm=function(){return this.each(function(){var t=e(this),r=this.tagName.toLowerCase();switch(r){case"input":this.checked=this.defaultChecked;case"textarea":return this.value=this.defaultValue,!0;case"option":case"optgroup":var a=t.parents("select");return a.length&&a[0].multiple?"option"===r?this.selected=this.defaultSelected:t.find("option").resetForm():a.resetForm(),!0;case"select":return t.find("option").each(function(e){if(this.selected=this.defaultSelected,this.defaultSelected&&!t[0].multiple)return t[0].selectedIndex=e,!1}),!0;case"label":var n=e(t.attr("for")),i=t.find("input,select,textarea");return n[0]&&i.unshift(n[0]),i.resetForm(),!0;case"form":return("function"==typeof this.reset||"object"==typeof this.reset&&!this.reset.nodeType)&&this.reset(),!0;default:return t.find("form,input,label,select,textarea").resetForm(),!0}})},e.fn.enable=function(e){return void 0===e&&(e=!0),this.each(function(){this.disabled=!e})},e.fn.selected=function(t){return void 0===t&&(t=!0),this.each(function(){var r=this.type;if("checkbox"===r||"radio"===r)this.checked=t;else if("option"===this.tagName.toLowerCase()){var a=e(this).parent("select");t&&a[0]&&"select-one"===a[0].type&&a.find("option").selected(!1),this.selected=t}})},e.fn.ajaxSubmit.debug=!1});
/*! jquery-qrcode v0.14.0 - https://larsjung.de/jquery-qrcode/ */
 !function(r){"use strict";function t(t,e,n,o){function a(r,t){return r-=o,t-=o,0>r||r>=c||0>t||t>=c?!1:f.isDark(r,t)}function i(r,t,e,n){var o=u.isDark,a=1/l;u.isDark=function(i,u){var f=u*a,c=i*a,l=f+a,g=c+a;return o(i,u)&&(r>l||f>e||t>g||c>n)}}var u={},f=r(n,e);f.addData(t),f.make(),o=o||0;var c=f.getModuleCount(),l=f.getModuleCount()+2*o;return u.text=t,u.level=e,u.version=n,u.moduleCount=l,u.isDark=a,u.addBlank=i,u}function e(r,e,n,o,a){n=Math.max(1,n||1),o=Math.min(40,o||40);for(var i=n;o>=i;i+=1)try{return t(r,e,i,a)}catch(u){}}function n(r,t,e){var n=e.size,o="bold "+e.mSize*n+"px "+e.fontname,a=w("<canvas/>")[0].getContext("2d");a.font=o;var i=a.measureText(e.label).width,u=e.mSize,f=i/n,c=(1-f)*e.mPosX,l=(1-u)*e.mPosY,g=c+f,s=l+u,v=.01;1===e.mode?r.addBlank(0,l-v,n,s+v):r.addBlank(c-v,l-v,g+v,s+v),t.fillStyle=e.fontcolor,t.font=o,t.fillText(e.label,c*n,l*n+.75*e.mSize*n)}function o(r,t,e){var n=e.size,o=e.image.naturalWidth||1,a=e.image.naturalHeight||1,i=e.mSize,u=i*o/a,f=(1-u)*e.mPosX,c=(1-i)*e.mPosY,l=f+u,g=c+i,s=.01;3===e.mode?r.addBlank(0,c-s,n,g+s):r.addBlank(f-s,c-s,l+s,g+s),t.drawImage(e.image,f*n,c*n,u*n,i*n)}function a(r,t,e){w(e.background).is("img")?t.drawImage(e.background,0,0,e.size,e.size):e.background&&(t.fillStyle=e.background,t.fillRect(e.left,e.top,e.size,e.size));var a=e.mode;1===a||2===a?n(r,t,e):(3===a||4===a)&&o(r,t,e)}function i(r,t,e,n,o,a,i,u){r.isDark(i,u)&&t.rect(n,o,a,a)}function u(r,t,e,n,o,a,i,u,f,c){i?r.moveTo(t+a,e):r.moveTo(t,e),u?(r.lineTo(n-a,e),r.arcTo(n,e,n,o,a)):r.lineTo(n,e),f?(r.lineTo(n,o-a),r.arcTo(n,o,t,o,a)):r.lineTo(n,o),c?(r.lineTo(t+a,o),r.arcTo(t,o,t,e,a)):r.lineTo(t,o),i?(r.lineTo(t,e+a),r.arcTo(t,e,n,e,a)):r.lineTo(t,e)}function f(r,t,e,n,o,a,i,u,f,c){i&&(r.moveTo(t+a,e),r.lineTo(t,e),r.lineTo(t,e+a),r.arcTo(t,e,t+a,e,a)),u&&(r.moveTo(n-a,e),r.lineTo(n,e),r.lineTo(n,e+a),r.arcTo(n,e,n-a,e,a)),f&&(r.moveTo(n-a,o),r.lineTo(n,o),r.lineTo(n,o-a),r.arcTo(n,o,n-a,o,a)),c&&(r.moveTo(t+a,o),r.lineTo(t,o),r.lineTo(t,o-a),r.arcTo(t,o,t+a,o,a))}function c(r,t,e,n,o,a,i,c){var l=r.isDark,g=n+a,s=o+a,v=e.radius*a,h=i-1,d=i+1,w=c-1,m=c+1,y=l(i,c),T=l(h,w),p=l(h,c),B=l(h,m),A=l(i,m),E=l(d,m),k=l(d,c),M=l(d,w),C=l(i,w);y?u(t,n,o,g,s,v,!p&&!C,!p&&!A,!k&&!A,!k&&!C):f(t,n,o,g,s,v,p&&C&&T,p&&A&&B,k&&A&&E,k&&C&&M)}function l(r,t,e){var n,o,a=r.moduleCount,u=e.size/a,f=i;for(e.radius>0&&e.radius<=.5&&(f=c),t.beginPath(),n=0;a>n;n+=1)for(o=0;a>o;o+=1){var l=e.left+o*u,g=e.top+n*u,s=u;f(r,t,e,l,g,s,n,o)}if(w(e.fill).is("img")){t.strokeStyle="rgba(0,0,0,0.5)",t.lineWidth=2,t.stroke();var v=t.globalCompositeOperation;t.globalCompositeOperation="destination-out",t.fill(),t.globalCompositeOperation=v,t.clip(),t.drawImage(e.fill,0,0,e.size,e.size),t.restore()}else t.fillStyle=e.fill,t.fill()}function g(r,t){var n=e(t.text,t.ecLevel,t.minVersion,t.maxVersion,t.quiet);if(!n)return null;var o=w(r).data("qrcode",n),i=o[0].getContext("2d");return a(n,i,t),l(n,i,t),o}function s(r){var t=w("<canvas/>").attr("width",r.size).attr("height",r.size);return g(t,r)}function v(r){return w("<img/>").attr("src",s(r)[0].toDataURL("image/png"))}function h(r){var t=e(r.text,r.ecLevel,r.minVersion,r.maxVersion,r.quiet);if(!t)return null;var n,o,a=r.size,i=r.background,u=Math.floor,f=t.moduleCount,c=u(a/f),l=u(.5*(a-c*f)),g={position:"relative",left:0,top:0,padding:0,margin:0,width:a,height:a},s={position:"absolute",padding:0,margin:0,width:c,height:c,"background-color":r.fill},v=w("<div/>").data("qrcode",t).css(g);for(i&&v.css("background-color",i),n=0;f>n;n+=1)for(o=0;f>o;o+=1)t.isDark(n,o)&&w("<div/>").css(s).css({left:l+o*c,top:l+n*c}).appendTo(v);return v}function d(r){return m&&"canvas"===r.render?s(r):m&&"image"===r.render?v(r):h(r)}var w=window.jQuery,m=function(){var r=document.createElement("canvas");return!(!r.getContext||!r.getContext("2d"))}(),y={render:"canvas",minVersion:1,maxVersion:40,ecLevel:"L",left:0,top:0,size:200,fill:"#000",background:null,text:"no text",radius:0,quiet:0,mode:0,mSize:.1,mPosX:.5,mPosY:.5,label:"no label",fontname:"sans",fontcolor:"#000",image:null};w.fn.qrcode=function(r){var t=w.extend({},y,r);return this.each(function(r,e){"canvas"===e.nodeName.toLowerCase()?g(e,t):w(e).append(d(t))})}}(function(){var r=function(){function r(t,e){if("undefined"==typeof t.length)throw new Error(t.length+"/"+e);var n=function(){for(var r=0;r<t.length&&0==t[r];)r+=1;for(var n=new Array(t.length-r+e),o=0;o<t.length-r;o+=1)n[o]=t[o+r];return n}(),o={};return o.getAt=function(r){return n[r]},o.getLength=function(){return n.length},o.multiply=function(t){for(var e=new Array(o.getLength()+t.getLength()-1),n=0;n<o.getLength();n+=1)for(var a=0;a<t.getLength();a+=1)e[n+a]^=i.gexp(i.glog(o.getAt(n))+i.glog(t.getAt(a)));return r(e,0)},o.mod=function(t){if(o.getLength()-t.getLength()<0)return o;for(var e=i.glog(o.getAt(0))-i.glog(t.getAt(0)),n=new Array(o.getLength()),a=0;a<o.getLength();a+=1)n[a]=o.getAt(a);for(var a=0;a<t.getLength();a+=1)n[a]^=i.gexp(i.glog(t.getAt(a))+e);return r(n,0).mod(t)},o}var t=function(t,e){var o=236,i=17,l=t,g=n[e],s=null,v=0,d=null,w=new Array,m={},y=function(r,t){v=4*l+17,s=function(r){for(var t=new Array(r),e=0;r>e;e+=1){t[e]=new Array(r);for(var n=0;r>n;n+=1)t[e][n]=null}return t}(v),T(0,0),T(v-7,0),T(0,v-7),A(),B(),k(r,t),l>=7&&E(r),null==d&&(d=D(l,g,w)),M(d,t)},T=function(r,t){for(var e=-1;7>=e;e+=1)if(!(-1>=r+e||r+e>=v))for(var n=-1;7>=n;n+=1)-1>=t+n||t+n>=v||(e>=0&&6>=e&&(0==n||6==n)||n>=0&&6>=n&&(0==e||6==e)||e>=2&&4>=e&&n>=2&&4>=n?s[r+e][t+n]=!0:s[r+e][t+n]=!1)},p=function(){for(var r=0,t=0,e=0;8>e;e+=1){y(!0,e);var n=a.getLostPoint(m);(0==e||r>n)&&(r=n,t=e)}return t},B=function(){for(var r=8;v-8>r;r+=1)null==s[r][6]&&(s[r][6]=r%2==0);for(var t=8;v-8>t;t+=1)null==s[6][t]&&(s[6][t]=t%2==0)},A=function(){for(var r=a.getPatternPosition(l),t=0;t<r.length;t+=1)for(var e=0;e<r.length;e+=1){var n=r[t],o=r[e];if(null==s[n][o])for(var i=-2;2>=i;i+=1)for(var u=-2;2>=u;u+=1)-2==i||2==i||-2==u||2==u||0==i&&0==u?s[n+i][o+u]=!0:s[n+i][o+u]=!1}},E=function(r){for(var t=a.getBCHTypeNumber(l),e=0;18>e;e+=1){var n=!r&&1==(t>>e&1);s[Math.floor(e/3)][e%3+v-8-3]=n}for(var e=0;18>e;e+=1){var n=!r&&1==(t>>e&1);s[e%3+v-8-3][Math.floor(e/3)]=n}},k=function(r,t){for(var e=g<<3|t,n=a.getBCHTypeInfo(e),o=0;15>o;o+=1){var i=!r&&1==(n>>o&1);6>o?s[o][8]=i:8>o?s[o+1][8]=i:s[v-15+o][8]=i}for(var o=0;15>o;o+=1){var i=!r&&1==(n>>o&1);8>o?s[8][v-o-1]=i:9>o?s[8][15-o-1+1]=i:s[8][15-o-1]=i}s[v-8][8]=!r},M=function(r,t){for(var e=-1,n=v-1,o=7,i=0,u=a.getMaskFunction(t),f=v-1;f>0;f-=2)for(6==f&&(f-=1);;){for(var c=0;2>c;c+=1)if(null==s[n][f-c]){var l=!1;i<r.length&&(l=1==(r[i]>>>o&1));var g=u(n,f-c);g&&(l=!l),s[n][f-c]=l,o-=1,-1==o&&(i+=1,o=7)}if(n+=e,0>n||n>=v){n-=e,e=-e;break}}},C=function(t,e){for(var n=0,o=0,i=0,u=new Array(e.length),f=new Array(e.length),c=0;c<e.length;c+=1){var l=e[c].dataCount,g=e[c].totalCount-l;o=Math.max(o,l),i=Math.max(i,g),u[c]=new Array(l);for(var s=0;s<u[c].length;s+=1)u[c][s]=255&t.getBuffer()[s+n];n+=l;var v=a.getErrorCorrectPolynomial(g),h=r(u[c],v.getLength()-1),d=h.mod(v);f[c]=new Array(v.getLength()-1);for(var s=0;s<f[c].length;s+=1){var w=s+d.getLength()-f[c].length;f[c][s]=w>=0?d.getAt(w):0}}for(var m=0,s=0;s<e.length;s+=1)m+=e[s].totalCount;for(var y=new Array(m),T=0,s=0;o>s;s+=1)for(var c=0;c<e.length;c+=1)s<u[c].length&&(y[T]=u[c][s],T+=1);for(var s=0;i>s;s+=1)for(var c=0;c<e.length;c+=1)s<f[c].length&&(y[T]=f[c][s],T+=1);return y},D=function(r,t,e){for(var n=u.getRSBlocks(r,t),c=f(),l=0;l<e.length;l+=1){var g=e[l];c.put(g.getMode(),4),c.put(g.getLength(),a.getLengthInBits(g.getMode(),r)),g.write(c)}for(var s=0,l=0;l<n.length;l+=1)s+=n[l].dataCount;if(c.getLengthInBits()>8*s)throw new Error("code length overflow. ("+c.getLengthInBits()+">"+8*s+")");for(c.getLengthInBits()+4<=8*s&&c.put(0,4);c.getLengthInBits()%8!=0;)c.putBit(!1);for(;;){if(c.getLengthInBits()>=8*s)break;if(c.put(o,8),c.getLengthInBits()>=8*s)break;c.put(i,8)}return C(c,n)};return m.addData=function(r){var t=c(r);w.push(t),d=null},m.isDark=function(r,t){if(0>r||r>=v||0>t||t>=v)throw new Error(r+","+t);return s[r][t]},m.getModuleCount=function(){return v},m.make=function(){y(!1,p())},m.createTableTag=function(r,t){r=r||2,t="undefined"==typeof t?4*r:t;var e="";e+='<table style="',e+=" border-width: 0px; border-style: none;",e+=" border-collapse: collapse;",e+=" padding: 0px; margin: "+t+"px;",e+='">',e+="<tbody>";for(var n=0;n<m.getModuleCount();n+=1){e+="<tr>";for(var o=0;o<m.getModuleCount();o+=1)e+='<td style="',e+=" border-width: 0px; border-style: none;",e+=" border-collapse: collapse;",e+=" padding: 0px; margin: 0px;",e+=" width: "+r+"px;",e+=" height: "+r+"px;",e+=" background-color: ",e+=m.isDark(n,o)?"#000000":"#ffffff",e+=";",e+='"/>';e+="</tr>"}return e+="</tbody>",e+="</table>"},m.createImgTag=function(r,t){r=r||2,t="undefined"==typeof t?4*r:t;var e=m.getModuleCount()*r+2*t,n=t,o=e-t;return h(e,e,function(t,e){if(t>=n&&o>t&&e>=n&&o>e){var a=Math.floor((t-n)/r),i=Math.floor((e-n)/r);return m.isDark(i,a)?0:1}return 1})},m};t.stringToBytes=function(r){for(var t=new Array,e=0;e<r.length;e+=1){var n=r.charCodeAt(e);t.push(255&n)}return t},t.createStringToBytes=function(r,t){var e=function(){for(var e=s(r),n=function(){var r=e.read();if(-1==r)throw new Error;return r},o=0,a={};;){var i=e.read();if(-1==i)break;var u=n(),f=n(),c=n(),l=String.fromCharCode(i<<8|u),g=f<<8|c;a[l]=g,o+=1}if(o!=t)throw new Error(o+" != "+t);return a}(),n="?".charCodeAt(0);return function(r){for(var t=new Array,o=0;o<r.length;o+=1){var a=r.charCodeAt(o);if(128>a)t.push(a);else{var i=e[r.charAt(o)];"number"==typeof i?(255&i)==i?t.push(i):(t.push(i>>>8),t.push(255&i)):t.push(n)}}return t}};var e={MODE_NUMBER:1,MODE_ALPHA_NUM:2,MODE_8BIT_BYTE:4,MODE_KANJI:8},n={L:1,M:0,Q:3,H:2},o={PATTERN000:0,PATTERN001:1,PATTERN010:2,PATTERN011:3,PATTERN100:4,PATTERN101:5,PATTERN110:6,PATTERN111:7},a=function(){var t=[[],[6,18],[6,22],[6,26],[6,30],[6,34],[6,22,38],[6,24,42],[6,26,46],[6,28,50],[6,30,54],[6,32,58],[6,34,62],[6,26,46,66],[6,26,48,70],[6,26,50,74],[6,30,54,78],[6,30,56,82],[6,30,58,86],[6,34,62,90],[6,28,50,72,94],[6,26,50,74,98],[6,30,54,78,102],[6,28,54,80,106],[6,32,58,84,110],[6,30,58,86,114],[6,34,62,90,118],[6,26,50,74,98,122],[6,30,54,78,102,126],[6,26,52,78,104,130],[6,30,56,82,108,134],[6,34,60,86,112,138],[6,30,58,86,114,142],[6,34,62,90,118,146],[6,30,54,78,102,126,150],[6,24,50,76,102,128,154],[6,28,54,80,106,132,158],[6,32,58,84,110,136,162],[6,26,54,82,110,138,166],[6,30,58,86,114,142,170]],n=1335,a=7973,u=21522,f={},c=function(r){for(var t=0;0!=r;)t+=1,r>>>=1;return t};return f.getBCHTypeInfo=function(r){for(var t=r<<10;c(t)-c(n)>=0;)t^=n<<c(t)-c(n);return(r<<10|t)^u},f.getBCHTypeNumber=function(r){for(var t=r<<12;c(t)-c(a)>=0;)t^=a<<c(t)-c(a);return r<<12|t},f.getPatternPosition=function(r){return t[r-1]},f.getMaskFunction=function(r){switch(r){case o.PATTERN000:return function(r,t){return(r+t)%2==0};case o.PATTERN001:return function(r,t){return r%2==0};case o.PATTERN010:return function(r,t){return t%3==0};case o.PATTERN011:return function(r,t){return(r+t)%3==0};case o.PATTERN100:return function(r,t){return(Math.floor(r/2)+Math.floor(t/3))%2==0};case o.PATTERN101:return function(r,t){return r*t%2+r*t%3==0};case o.PATTERN110:return function(r,t){return(r*t%2+r*t%3)%2==0};case o.PATTERN111:return function(r,t){return(r*t%3+(r+t)%2)%2==0};default:throw new Error("bad maskPattern:"+r)}},f.getErrorCorrectPolynomial=function(t){for(var e=r([1],0),n=0;t>n;n+=1)e=e.multiply(r([1,i.gexp(n)],0));return e},f.getLengthInBits=function(r,t){if(t>=1&&10>t)switch(r){case e.MODE_NUMBER:return 10;case e.MODE_ALPHA_NUM:return 9;case e.MODE_8BIT_BYTE:return 8;case e.MODE_KANJI:return 8;default:throw new Error("mode:"+r)}else if(27>t)switch(r){case e.MODE_NUMBER:return 12;case e.MODE_ALPHA_NUM:return 11;case e.MODE_8BIT_BYTE:return 16;case e.MODE_KANJI:return 10;default:throw new Error("mode:"+r)}else{if(!(41>t))throw new Error("type:"+t);switch(r){case e.MODE_NUMBER:return 14;case e.MODE_ALPHA_NUM:return 13;case e.MODE_8BIT_BYTE:return 16;case e.MODE_KANJI:return 12;default:throw new Error("mode:"+r)}}},f.getLostPoint=function(r){for(var t=r.getModuleCount(),e=0,n=0;t>n;n+=1)for(var o=0;t>o;o+=1){for(var a=0,i=r.isDark(n,o),u=-1;1>=u;u+=1)if(!(0>n+u||n+u>=t))for(var f=-1;1>=f;f+=1)0>o+f||o+f>=t||(0!=u||0!=f)&&i==r.isDark(n+u,o+f)&&(a+=1);a>5&&(e+=3+a-5)}for(var n=0;t-1>n;n+=1)for(var o=0;t-1>o;o+=1){var c=0;r.isDark(n,o)&&(c+=1),r.isDark(n+1,o)&&(c+=1),r.isDark(n,o+1)&&(c+=1),r.isDark(n+1,o+1)&&(c+=1),(0==c||4==c)&&(e+=3)}for(var n=0;t>n;n+=1)for(var o=0;t-6>o;o+=1)r.isDark(n,o)&&!r.isDark(n,o+1)&&r.isDark(n,o+2)&&r.isDark(n,o+3)&&r.isDark(n,o+4)&&!r.isDark(n,o+5)&&r.isDark(n,o+6)&&(e+=40);for(var o=0;t>o;o+=1)for(var n=0;t-6>n;n+=1)r.isDark(n,o)&&!r.isDark(n+1,o)&&r.isDark(n+2,o)&&r.isDark(n+3,o)&&r.isDark(n+4,o)&&!r.isDark(n+5,o)&&r.isDark(n+6,o)&&(e+=40);for(var l=0,o=0;t>o;o+=1)for(var n=0;t>n;n+=1)r.isDark(n,o)&&(l+=1);var g=Math.abs(100*l/t/t-50)/5;return e+=10*g},f}(),i=function(){for(var r=new Array(256),t=new Array(256),e=0;8>e;e+=1)r[e]=1<<e;for(var e=8;256>e;e+=1)r[e]=r[e-4]^r[e-5]^r[e-6]^r[e-8];for(var e=0;255>e;e+=1)t[r[e]]=e;var n={};return n.glog=function(r){if(1>r)throw new Error("glog("+r+")");return t[r]},n.gexp=function(t){for(;0>t;)t+=255;for(;t>=256;)t-=255;return r[t]},n}(),u=function(){var r=[[1,26,19],[1,26,16],[1,26,13],[1,26,9],[1,44,34],[1,44,28],[1,44,22],[1,44,16],[1,70,55],[1,70,44],[2,35,17],[2,35,13],[1,100,80],[2,50,32],[2,50,24],[4,25,9],[1,134,108],[2,67,43],[2,33,15,2,34,16],[2,33,11,2,34,12],[2,86,68],[4,43,27],[4,43,19],[4,43,15],[2,98,78],[4,49,31],[2,32,14,4,33,15],[4,39,13,1,40,14],[2,121,97],[2,60,38,2,61,39],[4,40,18,2,41,19],[4,40,14,2,41,15],[2,146,116],[3,58,36,2,59,37],[4,36,16,4,37,17],[4,36,12,4,37,13],[2,86,68,2,87,69],[4,69,43,1,70,44],[6,43,19,2,44,20],[6,43,15,2,44,16],[4,101,81],[1,80,50,4,81,51],[4,50,22,4,51,23],[3,36,12,8,37,13],[2,116,92,2,117,93],[6,58,36,2,59,37],[4,46,20,6,47,21],[7,42,14,4,43,15],[4,133,107],[8,59,37,1,60,38],[8,44,20,4,45,21],[12,33,11,4,34,12],[3,145,115,1,146,116],[4,64,40,5,65,41],[11,36,16,5,37,17],[11,36,12,5,37,13],[5,109,87,1,110,88],[5,65,41,5,66,42],[5,54,24,7,55,25],[11,36,12,7,37,13],[5,122,98,1,123,99],[7,73,45,3,74,46],[15,43,19,2,44,20],[3,45,15,13,46,16],[1,135,107,5,136,108],[10,74,46,1,75,47],[1,50,22,15,51,23],[2,42,14,17,43,15],[5,150,120,1,151,121],[9,69,43,4,70,44],[17,50,22,1,51,23],[2,42,14,19,43,15],[3,141,113,4,142,114],[3,70,44,11,71,45],[17,47,21,4,48,22],[9,39,13,16,40,14],[3,135,107,5,136,108],[3,67,41,13,68,42],[15,54,24,5,55,25],[15,43,15,10,44,16],[4,144,116,4,145,117],[17,68,42],[17,50,22,6,51,23],[19,46,16,6,47,17],[2,139,111,7,140,112],[17,74,46],[7,54,24,16,55,25],[34,37,13],[4,151,121,5,152,122],[4,75,47,14,76,48],[11,54,24,14,55,25],[16,45,15,14,46,16],[6,147,117,4,148,118],[6,73,45,14,74,46],[11,54,24,16,55,25],[30,46,16,2,47,17],[8,132,106,4,133,107],[8,75,47,13,76,48],[7,54,24,22,55,25],[22,45,15,13,46,16],[10,142,114,2,143,115],[19,74,46,4,75,47],[28,50,22,6,51,23],[33,46,16,4,47,17],[8,152,122,4,153,123],[22,73,45,3,74,46],[8,53,23,26,54,24],[12,45,15,28,46,16],[3,147,117,10,148,118],[3,73,45,23,74,46],[4,54,24,31,55,25],[11,45,15,31,46,16],[7,146,116,7,147,117],[21,73,45,7,74,46],[1,53,23,37,54,24],[19,45,15,26,46,16],[5,145,115,10,146,116],[19,75,47,10,76,48],[15,54,24,25,55,25],[23,45,15,25,46,16],[13,145,115,3,146,116],[2,74,46,29,75,47],[42,54,24,1,55,25],[23,45,15,28,46,16],[17,145,115],[10,74,46,23,75,47],[10,54,24,35,55,25],[19,45,15,35,46,16],[17,145,115,1,146,116],[14,74,46,21,75,47],[29,54,24,19,55,25],[11,45,15,46,46,16],[13,145,115,6,146,116],[14,74,46,23,75,47],[44,54,24,7,55,25],[59,46,16,1,47,17],[12,151,121,7,152,122],[12,75,47,26,76,48],[39,54,24,14,55,25],[22,45,15,41,46,16],[6,151,121,14,152,122],[6,75,47,34,76,48],[46,54,24,10,55,25],[2,45,15,64,46,16],[17,152,122,4,153,123],[29,74,46,14,75,47],[49,54,24,10,55,25],[24,45,15,46,46,16],[4,152,122,18,153,123],[13,74,46,32,75,47],[48,54,24,14,55,25],[42,45,15,32,46,16],[20,147,117,4,148,118],[40,75,47,7,76,48],[43,54,24,22,55,25],[10,45,15,67,46,16],[19,148,118,6,149,119],[18,75,47,31,76,48],[34,54,24,34,55,25],[20,45,15,61,46,16]],t=function(r,t){var e={};return e.totalCount=r,e.dataCount=t,e},e={},o=function(t,e){switch(e){case n.L:return r[4*(t-1)+0];case n.M:return r[4*(t-1)+1];case n.Q:return r[4*(t-1)+2];case n.H:return r[4*(t-1)+3];default:return}};return e.getRSBlocks=function(r,e){var n=o(r,e);if("undefined"==typeof n)throw new Error("bad rs block @ typeNumber:"+r+"/errorCorrectLevel:"+e);for(var a=n.length/3,i=new Array,u=0;a>u;u+=1)for(var f=n[3*u+0],c=n[3*u+1],l=n[3*u+2],g=0;f>g;g+=1)i.push(t(c,l));return i},e}(),f=function(){var r=new Array,t=0,e={};return e.getBuffer=function(){return r},e.getAt=function(t){var e=Math.floor(t/8);return 1==(r[e]>>>7-t%8&1)},e.put=function(r,t){for(var n=0;t>n;n+=1)e.putBit(1==(r>>>t-n-1&1))},e.getLengthInBits=function(){return t},e.putBit=function(e){var n=Math.floor(t/8);r.length<=n&&r.push(0),e&&(r[n]|=128>>>t%8),t+=1},e},c=function(r){var n=e.MODE_8BIT_BYTE,o=t.stringToBytes(r),a={};return a.getMode=function(){return n},a.getLength=function(r){return o.length},a.write=function(r){for(var t=0;t<o.length;t+=1)r.put(o[t],8)},a},l=function(){var r=new Array,t={};return t.writeByte=function(t){r.push(255&t)},t.writeShort=function(r){t.writeByte(r),t.writeByte(r>>>8)},t.writeBytes=function(r,e,n){e=e||0,n=n||r.length;for(var o=0;n>o;o+=1)t.writeByte(r[o+e])},t.writeString=function(r){for(var e=0;e<r.length;e+=1)t.writeByte(r.charCodeAt(e))},t.toByteArray=function(){return r},t.toString=function(){var t="";t+="[";for(var e=0;e<r.length;e+=1)e>0&&(t+=","),t+=r[e];return t+="]"},t},g=function(){var r=0,t=0,e=0,n="",o={},a=function(r){n+=String.fromCharCode(i(63&r))},i=function(r){if(0>r);else{if(26>r)return 65+r;if(52>r)return 97+(r-26);if(62>r)return 48+(r-52);if(62==r)return 43;if(63==r)return 47}throw new Error("n:"+r)};return o.writeByte=function(n){for(r=r<<8|255&n,t+=8,e+=1;t>=6;)a(r>>>t-6),t-=6},o.flush=function(){if(t>0&&(a(r<<6-t),r=0,t=0),e%3!=0)for(var o=3-e%3,i=0;o>i;i+=1)n+="="},o.toString=function(){return n},o},s=function(r){var t=r,e=0,n=0,o=0,a={};a.read=function(){for(;8>o;){if(e>=t.length){if(0==o)return-1;throw new Error("unexpected end of file./"+o)}var r=t.charAt(e);if(e+=1,"="==r)return o=0,-1;r.match(/^\s$/)||(n=n<<6|i(r.charCodeAt(0)),o+=6)}var a=n>>>o-8&255;return o-=8,a};var i=function(r){if(r>=65&&90>=r)return r-65;if(r>=97&&122>=r)return r-97+26;if(r>=48&&57>=r)return r-48+52;if(43==r)return 62;if(47==r)return 63;throw new Error("c:"+r)};return a},v=function(r,t){var e=r,n=t,o=new Array(r*t),a={};a.setPixel=function(r,t,n){o[t*e+r]=n},a.write=function(r){r.writeString("GIF87a"),r.writeShort(e),r.writeShort(n),r.writeByte(128),r.writeByte(0),r.writeByte(0),r.writeByte(0),r.writeByte(0),r.writeByte(0),r.writeByte(255),r.writeByte(255),r.writeByte(255),r.writeString(","),r.writeShort(0),r.writeShort(0),r.writeShort(e),r.writeShort(n),r.writeByte(0);var t=2,o=u(t);r.writeByte(t);for(var a=0;o.length-a>255;)r.writeByte(255),r.writeBytes(o,a,255),a+=255;r.writeByte(o.length-a),r.writeBytes(o,a,o.length-a),r.writeByte(0),r.writeString(";")};var i=function(r){var t=r,e=0,n=0,o={};return o.write=function(r,o){if(r>>>o!=0)throw new Error("length over");for(;e+o>=8;)t.writeByte(255&(r<<e|n)),o-=8-e,r>>>=8-e,n=0,e=0;n=r<<e|n,e+=o},o.flush=function(){e>0&&t.writeByte(n)},o},u=function(r){for(var t=1<<r,e=(1<<r)+1,n=r+1,a=f(),u=0;t>u;u+=1)a.add(String.fromCharCode(u));a.add(String.fromCharCode(t)),a.add(String.fromCharCode(e));var c=l(),g=i(c);g.write(t,n);var s=0,v=String.fromCharCode(o[s]);for(s+=1;s<o.length;){var h=String.fromCharCode(o[s]);s+=1,a.contains(v+h)?v+=h:(g.write(a.indexOf(v),n),a.size()<4095&&(a.size()==1<<n&&(n+=1),a.add(v+h)),v=h)}return g.write(a.indexOf(v),n),g.write(e,n),g.flush(),c.toByteArray()},f=function(){var r={},t=0,e={};return e.add=function(n){if(e.contains(n))throw new Error("dup key:"+n);r[n]=t,t+=1},e.size=function(){return t},e.indexOf=function(t){return r[t]},e.contains=function(t){return"undefined"!=typeof r[t]},e};return a},h=function(r,t,e,n){for(var o=v(r,t),a=0;t>a;a+=1)for(var i=0;r>i;i+=1)o.setPixel(i,a,e(i,a));var u=l();o.write(u);for(var f=g(),c=u.toByteArray(),s=0;s<c.length;s+=1)f.writeByte(c[s]);f.flush();var h="";return h+="<img",h+=' src="',h+="data:image/gif;base64,",h+=f,h+='"',h+=' width="',h+=r,h+='"',h+=' height="',h+=t,h+='"',n&&(h+=' alt="',h+=n,h+='"'),h+="/>"};return t}();return function(r){"function"==typeof define&&define.amd?define([],r):"object"==typeof exports&&(module.exports=r())}(function(){return r}),!function(r){r.stringToBytes=function(r){function t(r){for(var t=[],e=0;e<r.length;e++){var n=r.charCodeAt(e);128>n?t.push(n):2048>n?t.push(192|n>>6,128|63&n):55296>n||n>=57344?t.push(224|n>>12,128|n>>6&63,128|63&n):(e++,n=65536+((1023&n)<<10|1023&r.charCodeAt(e)),t.push(240|n>>18,128|n>>12&63,128|n>>6&63,128|63&n))}return t}return t(r)}}(r),r}());
/*!
 * jQuery PathBrowser
 *
 * (c) 2012 SABnzbd Team, Inc. All rights reserved.
 *
 * Dual licensed under MIT or GPLv2 licenses
 *   http://en.wikipedia.org/wiki/MIT_License
 *   http://en.wikipedia.org/wiki/GNU_General_Public_License
 *
 * Changed by Safihre - 11 Nov 2015
*/
;(function($) {
    // Building object
    function FileBrowser(element) {
        // Initialize
        this.element = $(element);
        this.initialDir = null;
        this.currentBrowserPath = null;
        this.currentRequest = null;
        this.fileBrowserDialog = $('#filebrowser_modal .modal-body');
        this.fileBrowserTitle = this.element.data('title') || $('label[for="'+this.element.attr('id')+'"]').text() || '';

        // Start
        this.init()
    };

    // Adding button
    FileBrowser.prototype.init = function () {
        // Self-reference
        var self = this;

        // Small or big button
        buttonText = this.element.hasClass('fileBrowserSmall') ? '' : configTranslate.browseText;

        // Add button
        this.element.addClass('fileBrowserField').after(
            $('<button class="btn btn-default fileBrowser" type="button"><span class="glyphicon glyphicon-folder-open"></span> '+buttonText+'</button>').click(function () {
                self.openBrowser();
            })
        )
    }

    // Open browser-window
    FileBrowser.prototype.openBrowser = function() {
        // Self-reference
        var self = this;

        // set up the browser and launch the dialog
        // textbox (not saved) path > textbox (saved) path > none
        this.initialDir = this.element.val() || this.element.data('initialdir') ||  '';

        // If there's no seperator, it must be a relative path
        if(this.initialDir.split(folderSeperator).length < 2 && this.element.data('initialdir')) {
            this.initialDir = this.element.data('initialdir') + folderSeperator + this.element.val();
        }

        // Browse
        this.browse(this.initialDir , folderBrowseUrl);

        // Choose path and close modal
        $('#filebrowser_modal_accept').click(function() {
            // Is it a relative path?
            if(self.currentBrowserPath.indexOf(self.element.data('initialdir')) === 0) {
                // Remove start
                self.currentBrowserPath = self.currentBrowserPath.replace(self.element.data('initialdir')+folderSeperator, '');
                // If it's identical to the initial dir the replacement won't work
                if(self.currentBrowserPath == self.element.data('initialdir')) {
                    self.currentBrowserPath = '';
                }
            }

            // Changed?
            if(self.element.val() != self.currentBrowserPath) {
                self.element.val(self.currentBrowserPath);
                formHasChanged = true;
            }

            // Hide and stop default action
            $('#filebrowser_modal').modal('hide');
            return false;
        })

        // Show hidden folders
        $('#show_hidden_folders').off('change')
        $('#show_hidden_folders').on('change', function() {
            self.browse(self.currentBrowserPath , folderBrowseUrl);
        })

        // Use custom title instead of default and open modal
        $('#filebrowser_modal .modal-header h4').text(this.fileBrowserTitle);
        $('#filebrowser_modal').modal('show');
        return false;
    }

    FileBrowser.prototype.browse = function(path, endpoint) {
        // Self-reference
        var self = this;

        // Still loading
        if (this.currentRequest) this.currentRequest.abort();

        // Show hidden folders on Linux?
        var extraHidden = $('#show_hidden_folders').is(':checked') ? '&show_hidden_folders=1' : '';

        // Get current folders
        this.currentBrowserPath = path;
        this.currentRequest = $.getJSON(endpoint + extraHidden, { name: path }, function (data) {
            // Clean
            self.fileBrowserDialog.empty();

            // Make list
            var list = $('<div class="list-group">').appendTo(self.fileBrowserDialog);
            $.each(data.paths, function (i, entry) {
                // Title for first one
                if(i == 0) {
                    self.fileBrowserDialog.prepend($('<h4>').text(entry.current_path))
                    return
                }
                // Regular link
                link = $('<a class="list-group-item" href="javascript:void(0)" />').click(function () {
                    self.browse(entry.path, endpoint); }
                ).text(entry.name);
                // Back image
                if(entry.name == '..') {
                    $('<span class="glyphicon glyphicon-arrow-left"></span> ').prependTo(link);
                } else {
                    $('<span class="glyphicon glyphicon-folder-open"></span> ').prependTo(link);
                }
                // Add to list
                link.appendTo(list);
            });

        });
    }

    // Make sure we have unique instances
    $.fn.fileBrowser = function () {
        return this.each(function () {
            if (!$.data(this, 'plugin_FileBrowser')) {
                $.data(this, 'plugin_FileBrowser', new FileBrowser(this));
            }
        });
    }
})(jQuery);

/*
 * Takes the inputs-elements found in the current selector
 * and extracts the values into the provided data-object.
 */
$.fn.extractFormDataTo = function(target) {
    var inputs = $("input[type != 'submit'][type != 'button']", this);

    // could use .serializeArray() but that omits unchecked items
    inputs.each(function (i,elem) {
        target[elem.name] = elem.value;
    });

    var selects = $("select", this);

    selects.each(function (i,elem) {
        target[elem.name] = elem.value;
    });

    return this;
}

/*!
 * Config JS
 *
 * (c) 2015 SABnzbd Team, Inc. All rights reserved.
 */
function config_success() {
    $('.saveButton').each(function () {
        $(this).removeAttr("disabled").html('<span class="glyphicon glyphicon-ok"></span> '+configTranslate.saveChanges);
    });
    // Let us leave!
    formWasSubmitted = true;
    formHasChanged = false;
}
function config_failure() {
    $('.saveButton').each(function () {
        $(this).removeAttr("disabled").addClass('btn-danger').html('<span class="glyphicon glyphicon-remove"></span> '+configTranslate.failed);
    });
    // Can't go yet..
    formWasSubmitted = false;
}
function do_restart() {
    // Show overlay
    $('.main-restarting').show()

    // What template
    var switchedHTTPS = ($('#enable_https').is(':checked') == ($('#enable_https').data('original') === undefined))
    var portsUnchanged  = ($('#port').val() == $('#port').data('original')) && ($('#https_port').val() == $('#https_port').data('original'))

    // Are we on settings page or did nothing change?
    if(!$('body').hasClass('General') || (!switchedHTTPS && portsUnchanged)) {
        // Same as before
        var urlTotal = window.location.origin + urlBase
    } else {
        // Protocol and port depend on http(s) setting
        if($('#enable_https').is(':checked') && (window.location.protocol == 'https:' || !$('#https_port').val())) {
            // Https on and we visited this page from HTTPS
            var urlProtocol = 'https:';
            var urlPort = $('#https_port').val() ? $('#https_port').val() : $('#port').val();
        } else {
            // Regular
            var urlProtocol = 'http:';
            var urlPort = $('#port').val();
        }

        // We cannot make a good guess for the IP, so at least we assume that stays the same
        var urlTotal = urlProtocol + '//' + window.location.hostname + ':' + urlPort + urlBase;
    }

    // Show where we are going to connect
    $('.main-restarting .restarting-url').text(urlTotal)

    // Initiate restart
    $.ajax({ url: '../../config/restart?apikey=' + sabSession,
        complete: function() {
            // Keep counter of failures
            var failureCounter = 0;

            // Now we try until we can connect
            var refreshInterval = setInterval(function() {
                // We skip the first one
                if(failureCounter == 0) {
                    failureCounter = failureCounter+1;
                    return
                }
                $.ajax({ url: urlTotal,
                    success: function() {
                        // Back to base
                        location.href = urlTotal;
                    },
                    error: function(status, text) {
                        failureCounter = failureCounter+1;
                        // Too many failuers and we give up
                        if(failureCounter >= 6) {
                            // If the port has changed 'Access-Control-Allow-Origin' header will not allow
                            // us to check if the server is back up. So after 7 failures we redirect
                            // anyway in the hopes it works anyway..
                            location.href = urlTotal;
                        }
                    }
                })
            }, 4000)

            // Exception if we go from HTTPS to HTTP
            // (this is not allowed by browsers and all of the above will be ignored)
            if(window.location.protocol != urlProtocol) {
                // Saftey redirect after 20 sec
                setTimeout(function() {
                    location.href = urlTotal;
                }, 20*1000)
            }
        }
    });
}

// Remove obfusication
function removeObfuscation() {
    $('input[data-hide]').each(function(index, objInput) {
        $(objInput).attr('name', $(objInput).data('hide'))
    })
    return true
}

// Add coloring to rows (shorthand function)
function addRowColor() {
    // Have to do it seperate for each section
    $('.section').each(function(i, elmn) {
        $(elmn).find('.field-pair:visible').removeClass('even').filter(':even').addClass('even')
    })
}

$(document).ready(function () {
    /**
        Restart function
    **/
    $('.sabnzbd_restart').click(function () {
        $('.sabnzbd_restart').each(function () {
            $(this).attr("disabled", "disabled");
        });
        if (confirm(configTranslate.explainRestart.replace(/\<br(\s*\/|)\>/g, '\n'))) {
            $(this).attr("value", configTranslate.wizzardRestart);
            // Let us leave!
            formWasSubmitted = true;
            do_restart();
        }
        $('.sabnzbd_restart').each(function () {
            $(this).removeAttr("disabled");
        });
        return false;
    });

    /**
        Submit the form
    **/
    $('.fullform').ajaxForm({
        datatype: 'json',
        // But first remove Obfuscation!
        beforeSerialize: removeObfuscation,
        beforeSubmit: function () {
            $('.saveButton').each(function () {
                $(this).attr("disabled", "disabled").removeClass('btn-danger').html('<span class="glyphicon glyphicon-transfer"></span> ' + configTranslate.saving);
            });
        },
        success: function (json) {
            if (json.error) {
               $('#config_err_msg').text(json.error);
               alert(json.error)
               config_failure()
            } else if(json.value && json.value.restart_req) {
                // Trigger restart question
                if(confirm(configTranslate.needRestart + "\n" + configTranslate.buttonRestart + " SABnzbd?")) {
                    // No more questions
                    do_restart();
                } else {
                    $('#config_err_msg').text(" ");
                    setTimeout(config_success, 1000);
                }
            } else {
               $('#config_err_msg').text(" ");
               setTimeout(config_success, 1000);
            }
        },
        error: function () {
            config_failure()
        },
        timeout: 3000
    });

    /**
        Form changes tracking
    **/
    $(document).on("submit", "form", function(event){
        // Let us leave!
        formWasSubmitted = true;
        formHasChanged = false;
    });
    $('#content').on('change', 'form input[type!="submit"][type!="button"], form select, form textarea', function (e) {
        formHasChanged = true;
        formWasSubmitted = false;
    });
    window.onbeforeunload = function (e) {
        if (formHasChanged && !formWasSubmitted) {
            var message = configTranslate.confirmLeave, e = e || window.event;
            if (e) {
                e.returnValue = message;
            }
            return message;
        }
    }

    // Fix for touch devices needing double click on the menu
    $('.navbar-nav li a').on('touchstart', function(e) {
        $(this).click()
    })

    // Add hover to checkboxes (can't do it with CSS)
    $('input[type="checkbox"]').siblings('label').addClass('config-hover')
    $('input[type="checkbox"]').parents('label').addClass('config-hover')

    // Disable sections
    var checkDisabled = '#rating_enable, #enable_tv_sorting, #enable_movie_sorting, #enable_date_sorting'

    $(checkDisabled).on('change', function() {
        $(this).parent().nextAll().toggleClass('disabled')
    }).each(function() {
        if(!$(this).is(':checked')) {
            $(this).parent().nextAll().addClass('disabled')
        }
    })

    // Advanced or not?
    $('.advanced-button').on('change', function(event){
        localStorage.setItem('advanced-settings', !$('.advanced-settings').is(':visible'))
        $('.advanced-settings').toggle()
        addRowColor()
    })
    if(localStorage.getItem('advanced-settings') == 'true') {
        $('.advanced-settings').show()
        $('#advanced-settings-button').prop('checked', true)
        addRowColor()
    }
    addRowColor()
});

/*
* SEARCH FUNCTIONALITY
*/
// Make :contains() case-insensitive
$.expr[":"].contains = $.expr.createPseudo(function(arg) {
    return function( elem ) {
        return $(elem).text().toUpperCase().indexOf(arg.toUpperCase()) >= 0;
    };
});

// Create list of pages to check and empty contain for results
var arrPages = ['general', 'folders', 'switches', 'sorting', 'notify', 'special']
var pagesContainer = new Array(arrPages.length);

// Add trigger to focus on the field and load the results
$(document).ready(function() {
    $('#search-menu').on('shown.bs.dropdown', function(event) {
        // Focus so easy typing
        $('#search-box').focus()
        // Load things to search if we haven't yet
        if(!pagesContainer[0]) {
            $.each(arrPages, function(index, page) {
                $.get(rootURL + 'config/' + page + '/', function(data) {
                    pagesContainer[index] = $(data).find('label')
                });
            });
        }
    });

    // For the scrolling
    // *only* if we have anchor on the url
    if(window.location.hash) {
        // Sometimes the ID is non-existing
        try {
            // Could be an Advanced setting
            if(!$(window.location.hash).is(':visible')) {
                // Show advanced settings, but don't save in localStorage
                $('.advanced-settings').toggle()
            }
            // smooth scroll to the anchor id
            $('html, body').animate({
                scrollTop: $(window.location.hash).offset().top -100 + 'px'
            }, 750, 'swing');
            setTimeout(function() {
                $(window.location.hash).focus()
            }, 750)
        } catch(err) {}
    }
})

// Don't go too fast
var searchTimeout
function doConfigSearch(value) {
    // Cancel previous
    clearTimeout(searchTimeout)
    // Build new search
    var searchTerm = $(value).val().replace('"', '\"')
    var searchOutput = $('#search-dropdown')

    // Build new search
    searchTimeout = setTimeout(function() {
        // Clear the output
        searchOutput.find('li:not(:first)').remove()
        // Anything to search for?
        if (searchTerm.length < 2) return
        // Find some results!
        $.each(pagesContainer, function(page_index, results) {
            // Get the matches
            var subResults = results.filter(':contains("'+searchTerm+'")')
            if(subResults.length > 0) {
                // Add the section
                searchOutput.append('<li class="divider"></li>')
                searchOutput.append('<li class="dropdown-header">'+configTranslate.searchPages[page_index]+'</li>')
                $.each(subResults, function(index, result) {
                    searchOutput.append('<li><a href="'+rootURL + 'config/' + arrPages[page_index] +  '/#' + $(result).attr('for') +'">'+$(result).text()+'</a></li>')
                })
            }
        })
    }, 200)
}

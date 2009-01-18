// main.js is made up of jquery+plugins with the main.tmpl's refresh/event code further below

/*
 * jQuery JavaScript Library v1.3
 * http://jquery.com/
 *
 * Copyright (c) 2009 John Resig
 * Dual licensed under the MIT and GPL licenses.
 * http://docs.jquery.com/License
 *
 * Date: 2009-01-13 12:50:31 -0500 (Tue, 13 Jan 2009)
 * Revision: 6104
 */
(function(){var l=this,g,x=l.jQuery,o=l.$,n=l.jQuery=l.$=function(D,E){return new n.fn.init(D,E)},C=/^[^<]*(<(.|\s)+>)[^>]*$|^#([\w-]+)$/,f=/^.[^:#\[\.,]*$/;n.fn=n.prototype={init:function(D,G){D=D||document;if(D.nodeType){this[0]=D;this.length=1;this.context=D;return this}if(typeof D==="string"){var F=C.exec(D);if(F&&(F[1]||!G)){if(F[1]){D=n.clean([F[1]],G)}else{var H=document.getElementById(F[3]);if(H){if(H.id!=F[3]){return n().find(D)}var E=n(H);E.context=document;E.selector=D;return E}D=[]}}else{return n(G).find(D)}}else{if(n.isFunction(D)){return n(document).ready(D)}}if(D.selector&&D.context){this.selector=D.selector;this.context=D.context}return this.setArray(n.makeArray(D))},selector:"",jquery:"1.3",size:function(){return this.length},get:function(D){return D===g?n.makeArray(this):this[D]},pushStack:function(E,G,D){var F=n(E);F.prevObject=this;F.context=this.context;if(G==="find"){F.selector=this.selector+(this.selector?" ":"")+D}else{if(G){F.selector=this.selector+"."+G+"("+D+")"}}return F},setArray:function(D){this.length=0;Array.prototype.push.apply(this,D);return this},each:function(E,D){return n.each(this,E,D)},index:function(D){return n.inArray(D&&D.jquery?D[0]:D,this)},attr:function(E,G,F){var D=E;if(typeof E==="string"){if(G===g){return this[0]&&n[F||"attr"](this[0],E)}else{D={};D[E]=G}}return this.each(function(H){for(E in D){n.attr(F?this.style:this,E,n.prop(this,D[E],F,H,E))}})},css:function(D,E){if((D=="width"||D=="height")&&parseFloat(E)<0){E=g}return this.attr(D,E,"curCSS")},text:function(E){if(typeof E!=="object"&&E!=null){return this.empty().append((this[0]&&this[0].ownerDocument||document).createTextNode(E))}var D="";n.each(E||this,function(){n.each(this.childNodes,function(){if(this.nodeType!=8){D+=this.nodeType!=1?this.nodeValue:n.fn.text([this])}})});return D},wrapAll:function(D){if(this[0]){var E=n(D,this[0].ownerDocument).clone();if(this[0].parentNode){E.insertBefore(this[0])}E.map(function(){var F=this;while(F.firstChild){F=F.firstChild}return F}).append(this)}return this},wrapInner:function(D){return this.each(function(){n(this).contents().wrapAll(D)})},wrap:function(D){return this.each(function(){n(this).wrapAll(D)})},append:function(){return this.domManip(arguments,true,function(D){if(this.nodeType==1){this.appendChild(D)}})},prepend:function(){return this.domManip(arguments,true,function(D){if(this.nodeType==1){this.insertBefore(D,this.firstChild)}})},before:function(){return this.domManip(arguments,false,function(D){this.parentNode.insertBefore(D,this)})},after:function(){return this.domManip(arguments,false,function(D){this.parentNode.insertBefore(D,this.nextSibling)})},end:function(){return this.prevObject||n([])},push:[].push,find:function(D){if(this.length===1&&!/,/.test(D)){var F=this.pushStack([],"find",D);F.length=0;n.find(D,this[0],F);return F}else{var E=n.map(this,function(G){return n.find(D,G)});return this.pushStack(/[^+>] [^+>]/.test(D)?n.unique(E):E,"find",D)}},clone:function(E){var D=this.map(function(){if(!n.support.noCloneEvent&&!n.isXMLDoc(this)){var H=this.cloneNode(true),G=document.createElement("div");G.appendChild(H);return n.clean([G.innerHTML])[0]}else{return this.cloneNode(true)}});var F=D.find("*").andSelf().each(function(){if(this[h]!==g){this[h]=null}});if(E===true){this.find("*").andSelf().each(function(H){if(this.nodeType==3){return}var G=n.data(this,"events");for(var J in G){for(var I in G[J]){n.event.add(F[H],J,G[J][I],G[J][I].data)}}})}return D},filter:function(D){return this.pushStack(n.isFunction(D)&&n.grep(this,function(F,E){return D.call(F,E)})||n.multiFilter(D,n.grep(this,function(E){return E.nodeType===1})),"filter",D)},closest:function(D){var E=n.expr.match.POS.test(D)?n(D):null;return this.map(function(){var F=this;while(F&&F.ownerDocument){if(E?E.index(F)>-1:n(F).is(D)){return F}F=F.parentNode}})},not:function(D){if(typeof D==="string"){if(f.test(D)){return this.pushStack(n.multiFilter(D,this,true),"not",D)}else{D=n.multiFilter(D,this)}}var E=D.length&&D[D.length-1]!==g&&!D.nodeType;return this.filter(function(){return E?n.inArray(this,D)<0:this!=D})},add:function(D){return this.pushStack(n.unique(n.merge(this.get(),typeof D==="string"?n(D):n.makeArray(D))))},is:function(D){return !!D&&n.multiFilter(D,this).length>0},hasClass:function(D){return !!D&&this.is("."+D)},val:function(J){if(J===g){var D=this[0];if(D){if(n.nodeName(D,"option")){return(D.attributes.value||{}).specified?D.value:D.text}if(n.nodeName(D,"select")){var H=D.selectedIndex,K=[],L=D.options,G=D.type=="select-one";if(H<0){return null}for(var E=G?H:0,I=G?H+1:L.length;E<I;E++){var F=L[E];if(F.selected){J=n(F).val();if(G){return J}K.push(J)}}return K}return(D.value||"").replace(/\r/g,"")}return g}if(typeof J==="number"){J+=""}return this.each(function(){if(this.nodeType!=1){return}if(n.isArray(J)&&/radio|checkbox/.test(this.type)){this.checked=(n.inArray(this.value,J)>=0||n.inArray(this.name,J)>=0)}else{if(n.nodeName(this,"select")){var M=n.makeArray(J);n("option",this).each(function(){this.selected=(n.inArray(this.value,M)>=0||n.inArray(this.text,M)>=0)});if(!M.length){this.selectedIndex=-1}}else{this.value=J}}})},html:function(D){return D===g?(this[0]?this[0].innerHTML:null):this.empty().append(D)},replaceWith:function(D){return this.after(D).remove()},eq:function(D){return this.slice(D,+D+1)},slice:function(){return this.pushStack(Array.prototype.slice.apply(this,arguments),"slice",Array.prototype.slice.call(arguments).join(","))},map:function(D){return this.pushStack(n.map(this,function(F,E){return D.call(F,E,F)}))},andSelf:function(){return this.add(this.prevObject)},domManip:function(J,M,L){if(this[0]){var I=(this[0].ownerDocument||this[0]).createDocumentFragment(),F=n.clean(J,(this[0].ownerDocument||this[0]),I),H=I.firstChild,D=this.length>1?I.cloneNode(true):I;if(H){for(var G=0,E=this.length;G<E;G++){L.call(K(this[G],H),G>0?D.cloneNode(true):I)}}if(F){n.each(F,y)}}return this;function K(N,O){return M&&n.nodeName(N,"table")&&n.nodeName(O,"tr")?(N.getElementsByTagName("tbody")[0]||N.appendChild(N.ownerDocument.createElement("tbody"))):N}}};n.fn.init.prototype=n.fn;function y(D,E){if(E.src){n.ajax({url:E.src,async:false,dataType:"script"})}else{n.globalEval(E.text||E.textContent||E.innerHTML||"")}if(E.parentNode){E.parentNode.removeChild(E)}}function e(){return +new Date}n.extend=n.fn.extend=function(){var I=arguments[0]||{},G=1,H=arguments.length,D=false,F;if(typeof I==="boolean"){D=I;I=arguments[1]||{};G=2}if(typeof I!=="object"&&!n.isFunction(I)){I={}}if(H==G){I=this;--G}for(;G<H;G++){if((F=arguments[G])!=null){for(var E in F){var J=I[E],K=F[E];if(I===K){continue}if(D&&K&&typeof K==="object"&&!K.nodeType){I[E]=n.extend(D,J||(K.length!=null?[]:{}),K)}else{if(K!==g){I[E]=K}}}}}return I};var b=/z-?index|font-?weight|opacity|zoom|line-?height/i,p=document.defaultView||{},r=Object.prototype.toString;n.extend({noConflict:function(D){l.$=o;if(D){l.jQuery=x}return n},isFunction:function(D){return r.call(D)==="[object Function]"},isArray:function(D){return r.call(D)==="[object Array]"},isXMLDoc:function(D){return D.documentElement&&!D.body||D.tagName&&D.ownerDocument&&!D.ownerDocument.body},globalEval:function(F){F=n.trim(F);if(F){var E=document.getElementsByTagName("head")[0]||document.documentElement,D=document.createElement("script");D.type="text/javascript";if(n.support.scriptEval){D.appendChild(document.createTextNode(F))}else{D.text=F}E.insertBefore(D,E.firstChild);E.removeChild(D)}},nodeName:function(E,D){return E.nodeName&&E.nodeName.toUpperCase()==D.toUpperCase()},each:function(F,J,E){var D,G=0,H=F.length;if(E){if(H===g){for(D in F){if(J.apply(F[D],E)===false){break}}}else{for(;G<H;){if(J.apply(F[G++],E)===false){break}}}}else{if(H===g){for(D in F){if(J.call(F[D],D,F[D])===false){break}}}else{for(var I=F[0];G<H&&J.call(I,G,I)!==false;I=F[++G]){}}}return F},prop:function(G,H,F,E,D){if(n.isFunction(H)){H=H.call(G,E)}return typeof H==="number"&&F=="curCSS"&&!b.test(D)?H+"px":H},className:{add:function(D,E){n.each((E||"").split(/\s+/),function(F,G){if(D.nodeType==1&&!n.className.has(D.className,G)){D.className+=(D.className?" ":"")+G}})},remove:function(D,E){if(D.nodeType==1){D.className=E!==g?n.grep(D.className.split(/\s+/),function(F){return !n.className.has(E,F)}).join(" "):""}},has:function(E,D){return n.inArray(D,(E.className||E).toString().split(/\s+/))>-1}},swap:function(G,F,H){var D={};for(var E in F){D[E]=G.style[E];G.style[E]=F[E]}H.call(G);for(var E in F){G.style[E]=D[E]}},css:function(F,D,H){if(D=="width"||D=="height"){var J,E={position:"absolute",visibility:"hidden",display:"block"},I=D=="width"?["Left","Right"]:["Top","Bottom"];function G(){J=D=="width"?F.offsetWidth:F.offsetHeight;var L=0,K=0;n.each(I,function(){L+=parseFloat(n.curCSS(F,"padding"+this,true))||0;K+=parseFloat(n.curCSS(F,"border"+this+"Width",true))||0});J-=Math.round(L+K)}if(n(F).is(":visible")){G()}else{n.swap(F,E,G)}return Math.max(0,J)}return n.curCSS(F,D,H)},curCSS:function(H,E,F){var K,D=H.style;if(E=="opacity"&&!n.support.opacity){K=n.attr(D,"opacity");return K==""?"1":K}if(E.match(/float/i)){E=v}if(!F&&D&&D[E]){K=D[E]}else{if(p.getComputedStyle){if(E.match(/float/i)){E="float"}E=E.replace(/([A-Z])/g,"-$1").toLowerCase();var L=p.getComputedStyle(H,null);if(L){K=L.getPropertyValue(E)}if(E=="opacity"&&K==""){K="1"}}else{if(H.currentStyle){var I=E.replace(/\-(\w)/g,function(M,N){return N.toUpperCase()});K=H.currentStyle[E]||H.currentStyle[I];if(!/^\d+(px)?$/i.test(K)&&/^\d/.test(K)){var G=D.left,J=H.runtimeStyle.left;H.runtimeStyle.left=H.currentStyle.left;D.left=K||0;K=D.pixelLeft+"px";D.left=G;H.runtimeStyle.left=J}}}}return K},clean:function(E,J,H){J=J||document;if(typeof J.createElement==="undefined"){J=J.ownerDocument||J[0]&&J[0].ownerDocument||document}if(!H&&E.length===1&&typeof E[0]==="string"){var G=/^<(\w+)\s*\/?>$/.exec(E[0]);if(G){return[J.createElement(G[1])]}}var F=[],D=[],K=J.createElement("div");n.each(E,function(O,Q){if(typeof Q==="number"){Q+=""}if(!Q){return}if(typeof Q==="string"){Q=Q.replace(/(<(\w+)[^>]*?)\/>/g,function(S,T,R){return R.match(/^(abbr|br|col|img|input|link|meta|param|hr|area|embed)$/i)?S:T+"></"+R+">"});var N=n.trim(Q).toLowerCase();var P=!N.indexOf("<opt")&&[1,"<select multiple='multiple'>","</select>"]||!N.indexOf("<leg")&&[1,"<fieldset>","</fieldset>"]||N.match(/^<(thead|tbody|tfoot|colg|cap)/)&&[1,"<table>","</table>"]||!N.indexOf("<tr")&&[2,"<table><tbody>","</tbody></table>"]||(!N.indexOf("<td")||!N.indexOf("<th"))&&[3,"<table><tbody><tr>","</tr></tbody></table>"]||!N.indexOf("<col")&&[2,"<table><tbody></tbody><colgroup>","</colgroup></table>"]||!n.support.htmlSerialize&&[1,"div<div>","</div>"]||[0,"",""];K.innerHTML=P[1]+Q+P[2];while(P[0]--){K=K.lastChild}if(!n.support.tbody){var M=!N.indexOf("<table")&&N.indexOf("<tbody")<0?K.firstChild&&K.firstChild.childNodes:P[1]=="<table>"&&N.indexOf("<tbody")<0?K.childNodes:[];for(var L=M.length-1;L>=0;--L){if(n.nodeName(M[L],"tbody")&&!M[L].childNodes.length){M[L].parentNode.removeChild(M[L])}}}if(!n.support.leadingWhitespace&&/^\s/.test(Q)){K.insertBefore(J.createTextNode(Q.match(/^\s*/)[0]),K.firstChild)}Q=n.makeArray(K.childNodes)}if(Q.nodeType){F.push(Q)}else{F=n.merge(F,Q)}});if(H){for(var I=0;F[I];I++){if(n.nodeName(F[I],"script")&&(!F[I].type||F[I].type.toLowerCase()==="text/javascript")){D.push(F[I].parentNode?F[I].parentNode.removeChild(F[I]):F[I])}else{if(F[I].nodeType===1){F.splice.apply(F,[I+1,0].concat(n.makeArray(F[I].getElementsByTagName("script"))))}H.appendChild(F[I])}}return D}return F},attr:function(I,F,J){if(!I||I.nodeType==3||I.nodeType==8){return g}var G=!n.isXMLDoc(I),K=J!==g;F=G&&n.props[F]||F;if(I.tagName){var E=/href|src|style/.test(F);if(F=="selected"&&I.parentNode){I.parentNode.selectedIndex}if(F in I&&G&&!E){if(K){if(F=="type"&&n.nodeName(I,"input")&&I.parentNode){throw"type property can't be changed"}I[F]=J}if(n.nodeName(I,"form")&&I.getAttributeNode(F)){return I.getAttributeNode(F).nodeValue}if(F=="tabIndex"){var H=I.getAttributeNode("tabIndex");return H&&H.specified?H.value:I.nodeName.match(/^(a|area|button|input|object|select|textarea)$/i)?0:g}return I[F]}if(!n.support.style&&G&&F=="style"){return n.attr(I.style,"cssText",J)}if(K){I.setAttribute(F,""+J)}var D=!n.support.hrefNormalized&&G&&E?I.getAttribute(F,2):I.getAttribute(F);return D===null?g:D}if(!n.support.opacity&&F=="opacity"){if(K){I.zoom=1;I.filter=(I.filter||"").replace(/alpha\([^)]*\)/,"")+(parseInt(J)+""=="NaN"?"":"alpha(opacity="+J*100+")")}return I.filter&&I.filter.indexOf("opacity=")>=0?(parseFloat(I.filter.match(/opacity=([^)]*)/)[1])/100)+"":""}F=F.replace(/-([a-z])/ig,function(L,M){return M.toUpperCase()});if(K){I[F]=J}return I[F]},trim:function(D){return(D||"").replace(/^\s+|\s+$/g,"")},makeArray:function(F){var D=[];if(F!=null){var E=F.length;if(E==null||typeof F==="string"||n.isFunction(F)||F.setInterval){D[0]=F}else{while(E){D[--E]=F[E]}}}return D},inArray:function(F,G){for(var D=0,E=G.length;D<E;D++){if(G[D]===F){return D}}return -1},merge:function(G,D){var E=0,F,H=G.length;if(!n.support.getAll){while((F=D[E++])!=null){if(F.nodeType!=8){G[H++]=F}}}else{while((F=D[E++])!=null){G[H++]=F}}return G},unique:function(J){var E=[],D={};try{for(var F=0,G=J.length;F<G;F++){var I=n.data(J[F]);if(!D[I]){D[I]=true;E.push(J[F])}}}catch(H){E=J}return E},grep:function(E,I,D){var F=[];for(var G=0,H=E.length;G<H;G++){if(!D!=!I(E[G],G)){F.push(E[G])}}return F},map:function(D,I){var E=[];for(var F=0,G=D.length;F<G;F++){var H=I(D[F],F);if(H!=null){E[E.length]=H}}return E.concat.apply([],E)}});var B=navigator.userAgent.toLowerCase();n.browser={version:(B.match(/.+(?:rv|it|ra|ie)[\/: ]([\d.]+)/)||[0,"0"])[1],safari:/webkit/.test(B),opera:/opera/.test(B),msie:/msie/.test(B)&&!/opera/.test(B),mozilla:/mozilla/.test(B)&&!/(compatible|webkit)/.test(B)};n.each({parent:function(D){return D.parentNode},parents:function(D){return n.dir(D,"parentNode")},next:function(D){return n.nth(D,2,"nextSibling")},prev:function(D){return n.nth(D,2,"previousSibling")},nextAll:function(D){return n.dir(D,"nextSibling")},prevAll:function(D){return n.dir(D,"previousSibling")},siblings:function(D){return n.sibling(D.parentNode.firstChild,D)},children:function(D){return n.sibling(D.firstChild)},contents:function(D){return n.nodeName(D,"iframe")?D.contentDocument||D.contentWindow.document:n.makeArray(D.childNodes)}},function(D,E){n.fn[D]=function(F){var G=n.map(this,E);if(F&&typeof F=="string"){G=n.multiFilter(F,G)}return this.pushStack(n.unique(G),D,F)}});n.each({appendTo:"append",prependTo:"prepend",insertBefore:"before",insertAfter:"after",replaceAll:"replaceWith"},function(D,E){n.fn[D]=function(){var F=arguments;return this.each(function(){for(var G=0,H=F.length;G<H;G++){n(F[G])[E](this)}})}});n.each({removeAttr:function(D){n.attr(this,D,"");if(this.nodeType==1){this.removeAttribute(D)}},addClass:function(D){n.className.add(this,D)},removeClass:function(D){n.className.remove(this,D)},toggleClass:function(E,D){if(typeof D!=="boolean"){D=!n.className.has(this,E)}n.className[D?"add":"remove"](this,E)},remove:function(D){if(!D||n.filter(D,[this]).length){n("*",this).add([this]).each(function(){n.event.remove(this);n.removeData(this)});if(this.parentNode){this.parentNode.removeChild(this)}}},empty:function(){n(">*",this).remove();while(this.firstChild){this.removeChild(this.firstChild)}}},function(D,E){n.fn[D]=function(){return this.each(E,arguments)}});function j(D,E){return D[0]&&parseInt(n.curCSS(D[0],E,true),10)||0}var h="jQuery"+e(),u=0,z={};n.extend({cache:{},data:function(E,D,F){E=E==l?z:E;var G=E[h];if(!G){G=E[h]=++u}if(D&&!n.cache[G]){n.cache[G]={}}if(F!==g){n.cache[G][D]=F}return D?n.cache[G][D]:G},removeData:function(E,D){E=E==l?z:E;var G=E[h];if(D){if(n.cache[G]){delete n.cache[G][D];D="";for(D in n.cache[G]){break}if(!D){n.removeData(E)}}}else{try{delete E[h]}catch(F){if(E.removeAttribute){E.removeAttribute(h)}}delete n.cache[G]}},queue:function(E,D,G){if(E){D=(D||"fx")+"queue";var F=n.data(E,D);if(!F||n.isArray(G)){F=n.data(E,D,n.makeArray(G))}else{if(G){F.push(G)}}}return F},dequeue:function(G,F){var D=n.queue(G,F),E=D.shift();if(!F||F==="fx"){E=D[0]}if(E!==g){E.call(G)}}});n.fn.extend({data:function(D,F){var G=D.split(".");G[1]=G[1]?"."+G[1]:"";if(F===g){var E=this.triggerHandler("getData"+G[1]+"!",[G[0]]);if(E===g&&this.length){E=n.data(this[0],D)}return E===g&&G[1]?this.data(G[0]):E}else{return this.trigger("setData"+G[1]+"!",[G[0],F]).each(function(){n.data(this,D,F)})}},removeData:function(D){return this.each(function(){n.removeData(this,D)})},queue:function(D,E){if(typeof D!=="string"){E=D;D="fx"}if(E===g){return n.queue(this[0],D)}return this.each(function(){var F=n.queue(this,D,E);if(D=="fx"&&F.length==1){F[0].call(this)}})},dequeue:function(D){return this.each(function(){n.dequeue(this,D)})}});
/*
 * Sizzle CSS Selector Engine - v0.9.1
 *  Copyright 2009, The Dojo Foundation
 *  Released under the MIT, BSD, and GPL Licenses.
 *  More information: http://sizzlejs.com/
 */
(function(){var N=/((?:\((?:\([^()]+\)|[^()]+)+\)|\[(?:\[[^[\]]*\]|[^[\]]+)+\]|\\.|[^ >+~,(\[]+)+|[>+~])(\s*,\s*)?/g,I=0,F=Object.prototype.toString;var E=function(ae,S,aa,V){aa=aa||[];S=S||document;if(S.nodeType!==1&&S.nodeType!==9){return[]}if(!ae||typeof ae!=="string"){return aa}var ab=[],ac,Y,ah,ag,Z,R,Q=true;N.lastIndex=0;while((ac=N.exec(ae))!==null){ab.push(ac[1]);if(ac[2]){R=RegExp.rightContext;break}}if(ab.length>1&&G.match.POS.exec(ae)){if(ab.length===2&&G.relative[ab[0]]){var U="",X;while((X=G.match.POS.exec(ae))){U+=X[0];ae=ae.replace(G.match.POS,"")}Y=E.filter(U,E(/\s$/.test(ae)?ae+"*":ae,S))}else{Y=G.relative[ab[0]]?[S]:E(ab.shift(),S);while(ab.length){var P=[];ae=ab.shift();if(G.relative[ae]){ae+=ab.shift()}for(var af=0,ad=Y.length;af<ad;af++){E(ae,Y[af],P)}Y=P}}}else{var ai=V?{expr:ab.pop(),set:D(V)}:E.find(ab.pop(),ab.length===1&&S.parentNode?S.parentNode:S);Y=E.filter(ai.expr,ai.set);if(ab.length>0){ah=D(Y)}else{Q=false}while(ab.length){var T=ab.pop(),W=T;if(!G.relative[T]){T=""}else{W=ab.pop()}if(W==null){W=S}G.relative[T](ah,W,M(S))}}if(!ah){ah=Y}if(!ah){throw"Syntax error, unrecognized expression: "+(T||ae)}if(F.call(ah)==="[object Array]"){if(!Q){aa.push.apply(aa,ah)}else{if(S.nodeType===1){for(var af=0;ah[af]!=null;af++){if(ah[af]&&(ah[af]===true||ah[af].nodeType===1&&H(S,ah[af]))){aa.push(Y[af])}}}else{for(var af=0;ah[af]!=null;af++){if(ah[af]&&ah[af].nodeType===1){aa.push(Y[af])}}}}}else{D(ah,aa)}if(R){E(R,S,aa,V)}return aa};E.matches=function(P,Q){return E(P,null,null,Q)};E.find=function(V,S){var W,Q;if(!V){return[]}for(var R=0,P=G.order.length;R<P;R++){var T=G.order[R],Q;if((Q=G.match[T].exec(V))){var U=RegExp.leftContext;if(U.substr(U.length-1)!=="\\"){Q[1]=(Q[1]||"").replace(/\\/g,"");W=G.find[T](Q,S);if(W!=null){V=V.replace(G.match[T],"");break}}}}if(!W){W=S.getElementsByTagName("*")}return{set:W,expr:V}};E.filter=function(S,ac,ad,T){var Q=S,Y=[],ah=ac,V,ab;while(S&&ac.length){for(var U in G.filter){if((V=G.match[U].exec(S))!=null){var Z=G.filter[U],R=null,X=0,aa,ag;ab=false;if(ah==Y){Y=[]}if(G.preFilter[U]){V=G.preFilter[U](V,ah,ad,Y,T);if(!V){ab=aa=true}else{if(V===true){continue}else{if(V[0]===true){R=[];var W=null,af;for(var ae=0;(af=ah[ae])!==g;ae++){if(af&&W!==af){R.push(af);W=af}}}}}}if(V){for(var ae=0;(ag=ah[ae])!==g;ae++){if(ag){if(R&&ag!=R[X]){X++}aa=Z(ag,V,X,R);var P=T^!!aa;if(ad&&aa!=null){if(P){ab=true}else{ah[ae]=false}}else{if(P){Y.push(ag);ab=true}}}}}if(aa!==g){if(!ad){ah=Y}S=S.replace(G.match[U],"");if(!ab){return[]}break}}}S=S.replace(/\s*,\s*/,"");if(S==Q){if(ab==null){throw"Syntax error, unrecognized expression: "+S}else{break}}Q=S}return ah};var G=E.selectors={order:["ID","NAME","TAG"],match:{ID:/#((?:[\w\u00c0-\uFFFF_-]|\\.)+)/,CLASS:/\.((?:[\w\u00c0-\uFFFF_-]|\\.)+)/,NAME:/\[name=['"]*((?:[\w\u00c0-\uFFFF_-]|\\.)+)['"]*\]/,ATTR:/\[\s*((?:[\w\u00c0-\uFFFF_-]|\\.)+)\s*(?:(\S?=)\s*(['"]*)(.*?)\3|)\s*\]/,TAG:/^((?:[\w\u00c0-\uFFFF\*_-]|\\.)+)/,CHILD:/:(only|nth|last|first)-child(?:\((even|odd|[\dn+-]*)\))?/,POS:/:(nth|eq|gt|lt|first|last|even|odd)(?:\((\d*)\))?(?=[^-]|$)/,PSEUDO:/:((?:[\w\u00c0-\uFFFF_-]|\\.)+)(?:\((['"]*)((?:\([^\)]+\)|[^\2\(\)]*)+)\2\))?/},attrMap:{"class":"className","for":"htmlFor"},attrHandle:{href:function(P){return P.getAttribute("href")}},relative:{"+":function(T,Q){for(var R=0,P=T.length;R<P;R++){var S=T[R];if(S){var U=S.previousSibling;while(U&&U.nodeType!==1){U=U.previousSibling}T[R]=typeof Q==="string"?U||false:U===Q}}if(typeof Q==="string"){E.filter(Q,T,true)}},">":function(U,Q,V){if(typeof Q==="string"&&!/\W/.test(Q)){Q=V?Q:Q.toUpperCase();for(var R=0,P=U.length;R<P;R++){var T=U[R];if(T){var S=T.parentNode;U[R]=S.nodeName===Q?S:false}}}else{for(var R=0,P=U.length;R<P;R++){var T=U[R];if(T){U[R]=typeof Q==="string"?T.parentNode:T.parentNode===Q}}if(typeof Q==="string"){E.filter(Q,U,true)}}},"":function(S,Q,U){var R="done"+(I++),P=O;if(!Q.match(/\W/)){var T=Q=U?Q:Q.toUpperCase();P=L}P("parentNode",Q,R,S,T,U)},"~":function(S,Q,U){var R="done"+(I++),P=O;if(typeof Q==="string"&&!Q.match(/\W/)){var T=Q=U?Q:Q.toUpperCase();P=L}P("previousSibling",Q,R,S,T,U)}},find:{ID:function(Q,R){if(R.getElementById){var P=R.getElementById(Q[1]);return P?[P]:[]}},NAME:function(P,Q){return Q.getElementsByName?Q.getElementsByName(P[1]):null},TAG:function(P,Q){return Q.getElementsByTagName(P[1])}},preFilter:{CLASS:function(S,Q,R,P,U){S=" "+S[1].replace(/\\/g,"")+" ";for(var T=0;Q[T];T++){if(U^(" "+Q[T].className+" ").indexOf(S)>=0){if(!R){P.push(Q[T])}}else{if(R){Q[T]=false}}}return false},ID:function(P){return P[1].replace(/\\/g,"")},TAG:function(Q,P){for(var R=0;!P[R];R++){}return M(P[R])?Q[1]:Q[1].toUpperCase()},CHILD:function(P){if(P[1]=="nth"){var Q=/(-?)(\d*)n((?:\+|-)?\d*)/.exec(P[2]=="even"&&"2n"||P[2]=="odd"&&"2n+1"||!/\D/.test(P[2])&&"0n+"+P[2]||P[2]);P[2]=(Q[1]+(Q[2]||1))-0;P[3]=Q[3]-0}P[0]="done"+(I++);return P},ATTR:function(Q){var P=Q[1];if(G.attrMap[P]){Q[1]=G.attrMap[P]}if(Q[2]==="~="){Q[4]=" "+Q[4]+" "}return Q},PSEUDO:function(T,Q,R,P,U){if(T[1]==="not"){if(T[3].match(N).length>1){T[3]=E(T[3],null,null,Q)}else{var S=E.filter(T[3],Q,R,true^U);if(!R){P.push.apply(P,S)}return false}}else{if(G.match.POS.test(T[0])){return true}}return T},POS:function(P){P.unshift(true);return P}},filters:{enabled:function(P){return P.disabled===false&&P.type!=="hidden"},disabled:function(P){return P.disabled===true},checked:function(P){return P.checked===true},selected:function(P){P.parentNode.selectedIndex;return P.selected===true},parent:function(P){return !!P.firstChild},empty:function(P){return !P.firstChild},has:function(R,Q,P){return !!E(P[3],R).length},header:function(P){return/h\d/i.test(P.nodeName)},text:function(P){return"text"===P.type},radio:function(P){return"radio"===P.type},checkbox:function(P){return"checkbox"===P.type},file:function(P){return"file"===P.type},password:function(P){return"password"===P.type},submit:function(P){return"submit"===P.type},image:function(P){return"image"===P.type},reset:function(P){return"reset"===P.type},button:function(P){return"button"===P.type||P.nodeName.toUpperCase()==="BUTTON"},input:function(P){return/input|select|textarea|button/i.test(P.nodeName)}},setFilters:{first:function(Q,P){return P===0},last:function(R,Q,P,S){return Q===S.length-1},even:function(Q,P){return P%2===0},odd:function(Q,P){return P%2===1},lt:function(R,Q,P){return Q<P[3]-0},gt:function(R,Q,P){return Q>P[3]-0},nth:function(R,Q,P){return P[3]-0==Q},eq:function(R,Q,P){return P[3]-0==Q}},filter:{CHILD:function(P,S){var V=S[1],W=P.parentNode;var U="child"+W.childNodes.length;if(W&&(!W[U]||!P.nodeIndex)){var T=1;for(var Q=W.firstChild;Q;Q=Q.nextSibling){if(Q.nodeType==1){Q.nodeIndex=T++}}W[U]=T-1}if(V=="first"){return P.nodeIndex==1}else{if(V=="last"){return P.nodeIndex==W[U]}else{if(V=="only"){return W[U]==1}else{if(V=="nth"){var Y=false,R=S[2],X=S[3];if(R==1&&X==0){return true}if(R==0){if(P.nodeIndex==X){Y=true}}else{if((P.nodeIndex-X)%R==0&&(P.nodeIndex-X)/R>=0){Y=true}}return Y}}}}},PSEUDO:function(V,R,S,W){var Q=R[1],T=G.filters[Q];if(T){return T(V,S,R,W)}else{if(Q==="contains"){return(V.textContent||V.innerText||"").indexOf(R[3])>=0}else{if(Q==="not"){var U=R[3];for(var S=0,P=U.length;S<P;S++){if(U[S]===V){return false}}return true}}}},ID:function(Q,P){return Q.nodeType===1&&Q.getAttribute("id")===P},TAG:function(Q,P){return(P==="*"&&Q.nodeType===1)||Q.nodeName===P},CLASS:function(Q,P){return P.test(Q.className)},ATTR:function(T,R){var P=G.attrHandle[R[1]]?G.attrHandle[R[1]](T):T[R[1]]||T.getAttribute(R[1]),U=P+"",S=R[2],Q=R[4];return P==null?false:S==="="?U===Q:S==="*="?U.indexOf(Q)>=0:S==="~="?(" "+U+" ").indexOf(Q)>=0:!R[4]?P:S==="!="?U!=Q:S==="^="?U.indexOf(Q)===0:S==="$="?U.substr(U.length-Q.length)===Q:S==="|="?U===Q||U.substr(0,Q.length+1)===Q+"-":false},POS:function(T,Q,R,U){var P=Q[2],S=G.setFilters[P];if(S){return S(T,R,Q,U)}}}};for(var K in G.match){G.match[K]=RegExp(G.match[K].source+/(?![^\[]*\])(?![^\(]*\))/.source)}var D=function(Q,P){Q=Array.prototype.slice.call(Q);if(P){P.push.apply(P,Q);return P}return Q};try{Array.prototype.slice.call(document.documentElement.childNodes)}catch(J){D=function(T,S){var Q=S||[];if(F.call(T)==="[object Array]"){Array.prototype.push.apply(Q,T)}else{if(typeof T.length==="number"){for(var R=0,P=T.length;R<P;R++){Q.push(T[R])}}else{for(var R=0;T[R];R++){Q.push(T[R])}}}return Q}}(function(){var Q=document.createElement("form"),R="script"+(new Date).getTime();Q.innerHTML="<input name='"+R+"'/>";var P=document.documentElement;P.insertBefore(Q,P.firstChild);if(!!document.getElementById(R)){G.find.ID=function(T,U){if(U.getElementById){var S=U.getElementById(T[1]);return S?S.id===T[1]||S.getAttributeNode&&S.getAttributeNode("id").nodeValue===T[1]?[S]:g:[]}};G.filter.ID=function(U,S){var T=U.getAttributeNode&&U.getAttributeNode("id");return U.nodeType===1&&T&&T.nodeValue===S}}P.removeChild(Q)})();(function(){var P=document.createElement("div");P.appendChild(document.createComment(""));if(P.getElementsByTagName("*").length>0){G.find.TAG=function(Q,U){var T=U.getElementsByTagName(Q[1]);if(Q[1]==="*"){var S=[];for(var R=0;T[R];R++){if(T[R].nodeType===1){S.push(T[R])}}T=S}return T}}P.innerHTML="<a href='#'></a>";if(P.firstChild.getAttribute("href")!=="#"){G.attrHandle.href=function(Q){return Q.getAttribute("href",2)}}})();if(document.querySelectorAll){(function(){var P=E;E=function(T,S,Q,R){S=S||document;if(!R&&S.nodeType===9){try{return D(S.querySelectorAll(T),Q)}catch(U){}}return P(T,S,Q,R)};E.find=P.find;E.filter=P.filter;E.selectors=P.selectors;E.matches=P.matches})()}if(document.documentElement.getElementsByClassName){G.order.splice(1,0,"CLASS");G.find.CLASS=function(P,Q){return Q.getElementsByClassName(P[1])}}function L(Q,W,V,Z,X,Y){for(var T=0,R=Z.length;T<R;T++){var P=Z[T];if(P){P=P[Q];var U=false;while(P&&P.nodeType){var S=P[V];if(S){U=Z[S];break}if(P.nodeType===1&&!Y){P[V]=T}if(P.nodeName===W){U=P;break}P=P[Q]}Z[T]=U}}}function O(Q,V,U,Y,W,X){for(var S=0,R=Y.length;S<R;S++){var P=Y[S];if(P){P=P[Q];var T=false;while(P&&P.nodeType){if(P[U]){T=Y[P[U]];break}if(P.nodeType===1){if(!X){P[U]=S}if(typeof V!=="string"){if(P===V){T=true;break}}else{if(E.filter(V,[P]).length>0){T=P;break}}}P=P[Q]}Y[S]=T}}}var H=document.compareDocumentPosition?function(Q,P){return Q.compareDocumentPosition(P)&16}:function(Q,P){return Q!==P&&(Q.contains?Q.contains(P):true)};var M=function(P){return P.documentElement&&!P.body||P.tagName&&P.ownerDocument&&!P.ownerDocument.body};n.find=E;n.filter=E.filter;n.expr=E.selectors;n.expr[":"]=n.expr.filters;E.selectors.filters.hidden=function(P){return"hidden"===P.type||n.css(P,"display")==="none"||n.css(P,"visibility")==="hidden"};E.selectors.filters.visible=function(P){return"hidden"!==P.type&&n.css(P,"display")!=="none"&&n.css(P,"visibility")!=="hidden"};E.selectors.filters.animated=function(P){return n.grep(n.timers,function(Q){return P===Q.elem}).length};n.multiFilter=function(R,P,Q){if(Q){R=":not("+R+")"}return E.matches(R,P)};n.dir=function(R,Q){var P=[],S=R[Q];while(S&&S!=document){if(S.nodeType==1){P.push(S)}S=S[Q]}return P};n.nth=function(T,P,R,S){P=P||1;var Q=0;for(;T;T=T[R]){if(T.nodeType==1&&++Q==P){break}}return T};n.sibling=function(R,Q){var P=[];for(;R;R=R.nextSibling){if(R.nodeType==1&&R!=Q){P.push(R)}}return P};return;l.Sizzle=E})();n.event={add:function(H,E,G,J){if(H.nodeType==3||H.nodeType==8){return}if(H.setInterval&&H!=l){H=l}if(!G.guid){G.guid=this.guid++}if(J!==g){var F=G;G=this.proxy(F);G.data=J}var D=n.data(H,"events")||n.data(H,"events",{}),I=n.data(H,"handle")||n.data(H,"handle",function(){return typeof n!=="undefined"&&!n.event.triggered?n.event.handle.apply(arguments.callee.elem,arguments):g});I.elem=H;n.each(E.split(/\s+/),function(L,M){var N=M.split(".");M=N.shift();G.type=N.slice().sort().join(".");var K=D[M];if(n.event.specialAll[M]){n.event.specialAll[M].setup.call(H,J,N)}if(!K){K=D[M]={};if(!n.event.special[M]||n.event.special[M].setup.call(H,J,N)===false){if(H.addEventListener){H.addEventListener(M,I,false)}else{if(H.attachEvent){H.attachEvent("on"+M,I)}}}}K[G.guid]=G;n.event.global[M]=true});H=null},guid:1,global:{},remove:function(J,G,I){if(J.nodeType==3||J.nodeType==8){return}var F=n.data(J,"events"),E,D;if(F){if(G===g||(typeof G==="string"&&G.charAt(0)==".")){for(var H in F){this.remove(J,H+(G||""))}}else{if(G.type){I=G.handler;G=G.type}n.each(G.split(/\s+/),function(L,N){var P=N.split(".");N=P.shift();var M=RegExp("(^|\\.)"+P.slice().sort().join(".*\\.")+"(\\.|$)");if(F[N]){if(I){delete F[N][I.guid]}else{for(var O in F[N]){if(M.test(F[N][O].type)){delete F[N][O]}}}if(n.event.specialAll[N]){n.event.specialAll[N].teardown.call(J,P)}for(E in F[N]){break}if(!E){if(!n.event.special[N]||n.event.special[N].teardown.call(J,P)===false){if(J.removeEventListener){J.removeEventListener(N,n.data(J,"handle"),false)}else{if(J.detachEvent){J.detachEvent("on"+N,n.data(J,"handle"))}}}E=null;delete F[N]}}})}for(E in F){break}if(!E){var K=n.data(J,"handle");if(K){K.elem=null}n.removeData(J,"events");n.removeData(J,"handle")}}},trigger:function(H,J,G,D){var F=H.type||H;if(!D){H=typeof H==="object"?H[h]?H:n.extend(n.Event(F),H):n.Event(F);if(F.indexOf("!")>=0){H.type=F=F.slice(0,-1);H.exclusive=true}if(!G){H.stopPropagation();if(this.global[F]){n.each(n.cache,function(){if(this.events&&this.events[F]){n.event.trigger(H,J,this.handle.elem)}})}}if(!G||G.nodeType==3||G.nodeType==8){return g}H.result=g;H.target=G;J=n.makeArray(J);J.unshift(H)}H.currentTarget=G;var I=n.data(G,"handle");if(I){I.apply(G,J)}if((!G[F]||(n.nodeName(G,"a")&&F=="click"))&&G["on"+F]&&G["on"+F].apply(G,J)===false){H.result=false}if(!D&&G[F]&&!H.isDefaultPrevented()&&!(n.nodeName(G,"a")&&F=="click")){this.triggered=true;try{G[F]()}catch(K){}}this.triggered=false;if(!H.isPropagationStopped()){var E=G.parentNode||G.ownerDocument;if(E){n.event.trigger(H,J,E,true)}}},handle:function(J){var I,D;J=arguments[0]=n.event.fix(J||l.event);var K=J.type.split(".");J.type=K.shift();I=!K.length&&!J.exclusive;var H=RegExp("(^|\\.)"+K.slice().sort().join(".*\\.")+"(\\.|$)");D=(n.data(this,"events")||{})[J.type];for(var F in D){var G=D[F];if(I||H.test(G.type)){J.handler=G;J.data=G.data;var E=G.apply(this,arguments);if(E!==g){J.result=E;if(E===false){J.preventDefault();J.stopPropagation()}}if(J.isImmediatePropagationStopped()){break}}}},props:"altKey attrChange attrName bubbles button cancelable charCode clientX clientY ctrlKey currentTarget data detail eventPhase fromElement handler keyCode metaKey newValue originalTarget pageX pageY prevValue relatedNode relatedTarget screenX screenY shiftKey srcElement target toElement view wheelDelta which".split(" "),fix:function(G){if(G[h]){return G}var E=G;G=n.Event(E);for(var F=this.props.length,I;F;){I=this.props[--F];G[I]=E[I]}if(!G.target){G.target=G.srcElement||document}if(G.target.nodeType==3){G.target=G.target.parentNode}if(!G.relatedTarget&&G.fromElement){G.relatedTarget=G.fromElement==G.target?G.toElement:G.fromElement}if(G.pageX==null&&G.clientX!=null){var H=document.documentElement,D=document.body;G.pageX=G.clientX+(H&&H.scrollLeft||D&&D.scrollLeft||0)-(H.clientLeft||0);G.pageY=G.clientY+(H&&H.scrollTop||D&&D.scrollTop||0)-(H.clientTop||0)}if(!G.which&&((G.charCode||G.charCode===0)?G.charCode:G.keyCode)){G.which=G.charCode||G.keyCode}if(!G.metaKey&&G.ctrlKey){G.metaKey=G.ctrlKey}if(!G.which&&G.button){G.which=(G.button&1?1:(G.button&2?3:(G.button&4?2:0)))}return G},proxy:function(E,D){D=D||function(){return E.apply(this,arguments)};D.guid=E.guid=E.guid||D.guid||this.guid++;return D},special:{ready:{setup:A,teardown:function(){}}},specialAll:{live:{setup:function(D,E){n.event.add(this,E[0],c)},teardown:function(F){if(F.length){var D=0,E=RegExp("(^|\\.)"+F[0]+"(\\.|$)");n.each((n.data(this,"events").live||{}),function(){if(E.test(this.type)){D++}});if(D<1){n.event.remove(this,F[0],c)}}}}}};n.Event=function(D){if(!this.preventDefault){return new n.Event(D)}if(D&&D.type){this.originalEvent=D;this.type=D.type;this.timeStamp=D.timeStamp}else{this.type=D}if(!this.timeStamp){this.timeStamp=e()}this[h]=true};function k(){return false}function t(){return true}n.Event.prototype={preventDefault:function(){this.isDefaultPrevented=t;var D=this.originalEvent;if(!D){return}if(D.preventDefault){D.preventDefault()}D.returnValue=false},stopPropagation:function(){this.isPropagationStopped=t;var D=this.originalEvent;if(!D){return}if(D.stopPropagation){D.stopPropagation()}D.cancelBubble=true},stopImmediatePropagation:function(){this.isImmediatePropagationStopped=t;this.stopPropagation()},isDefaultPrevented:k,isPropagationStopped:k,isImmediatePropagationStopped:k};var a=function(E){var D=E.relatedTarget;while(D&&D!=this){try{D=D.parentNode}catch(F){D=this}}if(D!=this){E.type=E.data;n.event.handle.apply(this,arguments)}};n.each({mouseover:"mouseenter",mouseout:"mouseleave"},function(E,D){n.event.special[D]={setup:function(){n.event.add(this,E,a,D)},teardown:function(){n.event.remove(this,E,a)}}});n.fn.extend({bind:function(E,F,D){return E=="unload"?this.one(E,F,D):this.each(function(){n.event.add(this,E,D||F,D&&F)})},one:function(F,G,E){var D=n.event.proxy(E||G,function(H){n(this).unbind(H,D);return(E||G).apply(this,arguments)});return this.each(function(){n.event.add(this,F,D,E&&G)})},unbind:function(E,D){return this.each(function(){n.event.remove(this,E,D)})},trigger:function(D,E){return this.each(function(){n.event.trigger(D,E,this)})},triggerHandler:function(D,F){if(this[0]){var E=n.Event(D);E.preventDefault();E.stopPropagation();n.event.trigger(E,F,this[0]);return E.result}},toggle:function(F){var D=arguments,E=1;while(E<D.length){n.event.proxy(F,D[E++])}return this.click(n.event.proxy(F,function(G){this.lastToggle=(this.lastToggle||0)%E;G.preventDefault();return D[this.lastToggle++].apply(this,arguments)||false}))},hover:function(D,E){return this.mouseenter(D).mouseleave(E)},ready:function(D){A();if(n.isReady){D.call(document,n)}else{n.readyList.push(D)}return this},live:function(F,E){var D=n.event.proxy(E);D.guid+=this.selector+F;n(document).bind(i(F,this.selector),this.selector,D);return this},die:function(E,D){n(document).unbind(i(E,this.selector),D?{guid:D.guid+this.selector+E}:null);return this}});function c(G){var D=RegExp("(^|\\.)"+G.type+"(\\.|$)"),F=true,E=[];n.each(n.data(this,"events").live||[],function(H,I){if(D.test(I.type)){var J=n(G.target).closest(I.data)[0];if(J){E.push({elem:J,fn:I})}}});n.each(E,function(){if(!G.isImmediatePropagationStopped()&&this.fn.call(this.elem,G,this.fn.data)===false){F=false}});return F}function i(E,D){return["live",E,D.replace(/\./g,"`").replace(/ /g,"|")].join(".")}n.extend({isReady:false,readyList:[],ready:function(){if(!n.isReady){n.isReady=true;if(n.readyList){n.each(n.readyList,function(){this.call(document,n)});n.readyList=null}n(document).triggerHandler("ready")}}});var w=false;function A(){if(w){return}w=true;if(document.addEventListener){document.addEventListener("DOMContentLoaded",function(){document.removeEventListener("DOMContentLoaded",arguments.callee,false);n.ready()},false)}else{if(document.attachEvent){document.attachEvent("onreadystatechange",function(){if(document.readyState==="complete"){document.detachEvent("onreadystatechange",arguments.callee);n.ready()}});if(document.documentElement.doScroll&&!l.frameElement){(function(){if(n.isReady){return}try{document.documentElement.doScroll("left")}catch(D){setTimeout(arguments.callee,0);return}n.ready()})()}}}n.event.add(l,"load",n.ready)}n.each(("blur,focus,load,resize,scroll,unload,click,dblclick,mousedown,mouseup,mousemove,mouseover,mouseout,mouseenter,mouseleave,change,select,submit,keydown,keypress,keyup,error").split(","),function(E,D){n.fn[D]=function(F){return F?this.bind(D,F):this.trigger(D)}});n(l).bind("unload",function(){for(var D in n.cache){if(D!=1&&n.cache[D].handle){n.event.remove(n.cache[D].handle.elem)}}});(function(){n.support={};var E=document.documentElement,F=document.createElement("script"),J=document.createElement("div"),I="script"+(new Date).getTime();J.style.display="none";J.innerHTML='   <link/><table></table><a href="/a" style="color:red;float:left;opacity:.5;">a</a><select><option>text</option></select><object><param/></object>';var G=J.getElementsByTagName("*"),D=J.getElementsByTagName("a")[0];if(!G||!G.length||!D){return}n.support={leadingWhitespace:J.firstChild.nodeType==3,tbody:!J.getElementsByTagName("tbody").length,objectAll:!!J.getElementsByTagName("object")[0].getElementsByTagName("*").length,htmlSerialize:!!J.getElementsByTagName("link").length,style:/red/.test(D.getAttribute("style")),hrefNormalized:D.getAttribute("href")==="/a",opacity:D.style.opacity==="0.5",cssFloat:!!D.style.cssFloat,scriptEval:false,noCloneEvent:true,boxModel:null};F.type="text/javascript";try{F.appendChild(document.createTextNode("window."+I+"=1;"))}catch(H){}E.insertBefore(F,E.firstChild);if(l[I]){n.support.scriptEval=true;delete l[I]}E.removeChild(F);if(J.attachEvent&&J.fireEvent){J.attachEvent("onclick",function(){n.support.noCloneEvent=false;J.detachEvent("onclick",arguments.callee)});J.cloneNode(true).fireEvent("onclick")}n(function(){var K=document.createElement("div");K.style.width="1px";K.style.paddingLeft="1px";document.body.appendChild(K);n.boxModel=n.support.boxModel=K.offsetWidth===2;document.body.removeChild(K)})})();var v=n.support.cssFloat?"cssFloat":"styleFloat";n.props={"for":"htmlFor","class":"className","float":v,cssFloat:v,styleFloat:v,readonly:"readOnly",maxlength:"maxLength",cellspacing:"cellSpacing",rowspan:"rowSpan",tabindex:"tabIndex"};n.fn.extend({_load:n.fn.load,load:function(F,I,J){if(typeof F!=="string"){return this._load(F)}var H=F.indexOf(" ");if(H>=0){var D=F.slice(H,F.length);F=F.slice(0,H)}var G="GET";if(I){if(n.isFunction(I)){J=I;I=null}else{if(typeof I==="object"){I=n.param(I);G="POST"}}}var E=this;n.ajax({url:F,type:G,dataType:"html",data:I,complete:function(L,K){if(K=="success"||K=="notmodified"){E.html(D?n("<div/>").append(L.responseText.replace(/<script(.|\s)*?\/script>/g,"")).find(D):L.responseText)}if(J){E.each(J,[L.responseText,K,L])}}});return this},serialize:function(){return n.param(this.serializeArray())},serializeArray:function(){return this.map(function(){return this.elements?n.makeArray(this.elements):this}).filter(function(){return this.name&&!this.disabled&&(this.checked||/select|textarea/i.test(this.nodeName)||/text|hidden|password/i.test(this.type))}).map(function(D,E){var F=n(this).val();return F==null?null:n.isArray(F)?n.map(F,function(H,G){return{name:E.name,value:H}}):{name:E.name,value:F}}).get()}});n.each("ajaxStart,ajaxStop,ajaxComplete,ajaxError,ajaxSuccess,ajaxSend".split(","),function(D,E){n.fn[E]=function(F){return this.bind(E,F)}});var q=e();n.extend({get:function(D,F,G,E){if(n.isFunction(F)){G=F;F=null}return n.ajax({type:"GET",url:D,data:F,success:G,dataType:E})},getScript:function(D,E){return n.get(D,null,E,"script")},getJSON:function(D,E,F){return n.get(D,E,F,"json")},post:function(D,F,G,E){if(n.isFunction(F)){G=F;F={}}return n.ajax({type:"POST",url:D,data:F,success:G,dataType:E})},ajaxSetup:function(D){n.extend(n.ajaxSettings,D)},ajaxSettings:{url:location.href,global:true,type:"GET",contentType:"application/x-www-form-urlencoded",processData:true,async:true,xhr:function(){return l.ActiveXObject?new ActiveXObject("Microsoft.XMLHTTP"):new XMLHttpRequest()},accepts:{xml:"application/xml, text/xml",html:"text/html",script:"text/javascript, application/javascript",json:"application/json, text/javascript",text:"text/plain",_default:"*/*"}},lastModified:{},ajax:function(L){L=n.extend(true,L,n.extend(true,{},n.ajaxSettings,L));var V,E=/=\?(&|$)/g,Q,U,F=L.type.toUpperCase();if(L.data&&L.processData&&typeof L.data!=="string"){L.data=n.param(L.data)}if(L.dataType=="jsonp"){if(F=="GET"){if(!L.url.match(E)){L.url+=(L.url.match(/\?/)?"&":"?")+(L.jsonp||"callback")+"=?"}}else{if(!L.data||!L.data.match(E)){L.data=(L.data?L.data+"&":"")+(L.jsonp||"callback")+"=?"}}L.dataType="json"}if(L.dataType=="json"&&(L.data&&L.data.match(E)||L.url.match(E))){V="jsonp"+q++;if(L.data){L.data=(L.data+"").replace(E,"="+V+"$1")}L.url=L.url.replace(E,"="+V+"$1");L.dataType="script";l[V]=function(W){U=W;H();K();l[V]=g;try{delete l[V]}catch(X){}if(G){G.removeChild(S)}}}if(L.dataType=="script"&&L.cache==null){L.cache=false}if(L.cache===false&&F=="GET"){var D=e();var T=L.url.replace(/(\?|&)_=.*?(&|$)/,"$1_="+D+"$2");L.url=T+((T==L.url)?(L.url.match(/\?/)?"&":"?")+"_="+D:"")}if(L.data&&F=="GET"){L.url+=(L.url.match(/\?/)?"&":"?")+L.data;L.data=null}if(L.global&&!n.active++){n.event.trigger("ajaxStart")}var P=/^(\w+:)?\/\/([^\/?#]+)/.exec(L.url);if(L.dataType=="script"&&F=="GET"&&P&&(P[1]&&P[1]!=location.protocol||P[2]!=location.host)){var G=document.getElementsByTagName("head")[0];var S=document.createElement("script");S.src=L.url;if(L.scriptCharset){S.charset=L.scriptCharset}if(!V){var N=false;S.onload=S.onreadystatechange=function(){if(!N&&(!this.readyState||this.readyState=="loaded"||this.readyState=="complete")){N=true;H();K();G.removeChild(S)}}}G.appendChild(S);return g}var J=false;var I=L.xhr();if(L.username){I.open(F,L.url,L.async,L.username,L.password)}else{I.open(F,L.url,L.async)}try{if(L.data){I.setRequestHeader("Content-Type",L.contentType)}if(L.ifModified){I.setRequestHeader("If-Modified-Since",n.lastModified[L.url]||"Thu, 01 Jan 1970 00:00:00 GMT")}I.setRequestHeader("X-Requested-With","XMLHttpRequest");I.setRequestHeader("Accept",L.dataType&&L.accepts[L.dataType]?L.accepts[L.dataType]+", */*":L.accepts._default)}catch(R){}if(L.beforeSend&&L.beforeSend(I,L)===false){if(L.global&&!--n.active){n.event.trigger("ajaxStop")}I.abort();return false}if(L.global){n.event.trigger("ajaxSend",[I,L])}var M=function(W){if(I.readyState==0){if(O){clearInterval(O);O=null;if(L.global&&!--n.active){n.event.trigger("ajaxStop")}}}else{if(!J&&I&&(I.readyState==4||W=="timeout")){J=true;if(O){clearInterval(O);O=null}Q=W=="timeout"?"timeout":!n.httpSuccess(I)?"error":L.ifModified&&n.httpNotModified(I,L.url)?"notmodified":"success";if(Q=="success"){try{U=n.httpData(I,L.dataType,L)}catch(Y){Q="parsererror"}}if(Q=="success"){var X;try{X=I.getResponseHeader("Last-Modified")}catch(Y){}if(L.ifModified&&X){n.lastModified[L.url]=X}if(!V){H()}}else{n.handleError(L,I,Q)}K();if(L.async){I=null}}}};if(L.async){var O=setInterval(M,13);if(L.timeout>0){setTimeout(function(){if(I){if(!J){M("timeout")}if(I){I.abort()}}},L.timeout)}}try{I.send(L.data)}catch(R){n.handleError(L,I,null,R)}if(!L.async){M()}function H(){if(L.success){L.success(U,Q)}if(L.global){n.event.trigger("ajaxSuccess",[I,L])}}function K(){if(L.complete){L.complete(I,Q)}if(L.global){n.event.trigger("ajaxComplete",[I,L])}if(L.global&&!--n.active){n.event.trigger("ajaxStop")}}return I},handleError:function(E,G,D,F){if(E.error){E.error(G,D,F)}if(E.global){n.event.trigger("ajaxError",[G,E,F])}},active:0,httpSuccess:function(E){try{return !E.status&&location.protocol=="file:"||(E.status>=200&&E.status<300)||E.status==304||E.status==1223}catch(D){}return false},httpNotModified:function(F,D){try{var G=F.getResponseHeader("Last-Modified");return F.status==304||G==n.lastModified[D]}catch(E){}return false},httpData:function(I,G,F){var E=I.getResponseHeader("content-type"),D=G=="xml"||!G&&E&&E.indexOf("xml")>=0,H=D?I.responseXML:I.responseText;if(D&&H.documentElement.tagName=="parsererror"){throw"parsererror"}if(F&&F.dataFilter){H=F.dataFilter(H,G)}if(typeof H==="string"){if(G=="script"){n.globalEval(H)}if(G=="json"){H=l["eval"]("("+H+")")}}return H},param:function(D){var F=[];function G(H,I){F[F.length]=encodeURIComponent(H)+"="+encodeURIComponent(I)}if(n.isArray(D)||D.jquery){n.each(D,function(){G(this.name,this.value)})}else{for(var E in D){if(n.isArray(D[E])){n.each(D[E],function(){G(E,this)})}else{G(E,n.isFunction(D[E])?D[E]():D[E])}}}return F.join("&").replace(/%20/g,"+")}});var m={},d=[["height","marginTop","marginBottom","paddingTop","paddingBottom"],["width","marginLeft","marginRight","paddingLeft","paddingRight"],["opacity"]];function s(E,D){var F={};n.each(d.concat.apply([],d.slice(0,D)),function(){F[this]=E});return F}n.fn.extend({show:function(I,K){if(I){return this.animate(s("show",3),I,K)}else{for(var G=0,E=this.length;G<E;G++){var D=n.data(this[G],"olddisplay");this[G].style.display=D||"";if(n.css(this[G],"display")==="none"){var F=this[G].tagName,J;if(m[F]){J=m[F]}else{var H=n("<"+F+" />").appendTo("body");J=H.css("display");if(J==="none"){J="block"}H.remove();m[F]=J}this[G].style.display=n.data(this[G],"olddisplay",J)}}return this}},hide:function(G,H){if(G){return this.animate(s("hide",3),G,H)}else{for(var F=0,E=this.length;F<E;F++){var D=n.data(this[F],"olddisplay");if(!D&&D!=="none"){n.data(this[F],"olddisplay",n.css(this[F],"display"))}this[F].style.display="none"}return this}},_toggle:n.fn.toggle,toggle:function(F,E){var D=typeof F==="boolean";return n.isFunction(F)&&n.isFunction(E)?this._toggle.apply(this,arguments):F==null||D?this.each(function(){var G=D?F:n(this).is(":hidden");n(this)[G?"show":"hide"]()}):this.animate(s("toggle",3),F,E)},fadeTo:function(D,F,E){return this.animate({opacity:F},D,E)},animate:function(H,E,G,F){var D=n.speed(E,G,F);return this[D.queue===false?"each":"queue"](function(){var J=n.extend({},D),L,K=this.nodeType==1&&n(this).is(":hidden"),I=this;for(L in H){if(H[L]=="hide"&&K||H[L]=="show"&&!K){return J.complete.call(this)}if((L=="height"||L=="width")&&this.style){J.display=n.css(this,"display");J.overflow=this.style.overflow}}if(J.overflow!=null){this.style.overflow="hidden"}J.curAnim=n.extend({},H);n.each(H,function(N,R){var Q=new n.fx(I,J,N);if(/toggle|show|hide/.test(R)){Q[R=="toggle"?K?"show":"hide":R](H)}else{var P=R.toString().match(/^([+-]=)?([\d+-.]+)(.*)$/),S=Q.cur(true)||0;if(P){var M=parseFloat(P[2]),O=P[3]||"px";if(O!="px"){I.style[N]=(M||1)+O;S=((M||1)/Q.cur(true))*S;I.style[N]=S+O}if(P[1]){M=((P[1]=="-="?-1:1)*M)+S}Q.custom(S,M,O)}else{Q.custom(S,R,"")}}});return true})},stop:function(E,D){var F=n.timers;if(E){this.queue([])}this.each(function(){for(var G=F.length-1;G>=0;G--){if(F[G].elem==this){if(D){F[G](true)}F.splice(G,1)}}});if(!D){this.dequeue()}return this}});n.each({slideDown:s("show",1),slideUp:s("hide",1),slideToggle:s("toggle",1),fadeIn:{opacity:"show"},fadeOut:{opacity:"hide"}},function(D,E){n.fn[D]=function(F,G){return this.animate(E,F,G)}});n.extend({speed:function(F,G,E){var D=typeof F==="object"?F:{complete:E||!E&&G||n.isFunction(F)&&F,duration:F,easing:E&&G||G&&!n.isFunction(G)&&G};D.duration=n.fx.off?0:typeof D.duration==="number"?D.duration:n.fx.speeds[D.duration]||n.fx.speeds._default;D.old=D.complete;D.complete=function(){if(D.queue!==false){n(this).dequeue()}if(n.isFunction(D.old)){D.old.call(this)}};return D},easing:{linear:function(F,G,D,E){return D+E*F},swing:function(F,G,D,E){return((-Math.cos(F*Math.PI)/2)+0.5)*E+D}},timers:[],timerId:null,fx:function(E,D,F){this.options=D;this.elem=E;this.prop=F;if(!D.orig){D.orig={}}}});n.fx.prototype={update:function(){if(this.options.step){this.options.step.call(this.elem,this.now,this)}(n.fx.step[this.prop]||n.fx.step._default)(this);if((this.prop=="height"||this.prop=="width")&&this.elem.style){this.elem.style.display="block"}},cur:function(E){if(this.elem[this.prop]!=null&&(!this.elem.style||this.elem.style[this.prop]==null)){return this.elem[this.prop]}var D=parseFloat(n.css(this.elem,this.prop,E));return D&&D>-10000?D:parseFloat(n.curCSS(this.elem,this.prop))||0},custom:function(H,G,F){this.startTime=e();this.start=H;this.end=G;this.unit=F||this.unit||"px";this.now=this.start;this.pos=this.state=0;var D=this;function E(I){return D.step(I)}E.elem=this.elem;n.timers.push(E);if(E()&&n.timerId==null){n.timerId=setInterval(function(){var J=n.timers;for(var I=0;I<J.length;I++){if(!J[I]()){J.splice(I--,1)}}if(!J.length){clearInterval(n.timerId);n.timerId=null}},13)}},show:function(){this.options.orig[this.prop]=n.attr(this.elem.style,this.prop);this.options.show=true;this.custom(this.prop=="width"||this.prop=="height"?1:0,this.cur());n(this.elem).show()},hide:function(){this.options.orig[this.prop]=n.attr(this.elem.style,this.prop);this.options.hide=true;this.custom(this.cur(),0)},step:function(G){var F=e();if(G||F>=this.options.duration+this.startTime){this.now=this.end;this.pos=this.state=1;this.update();this.options.curAnim[this.prop]=true;var D=true;for(var E in this.options.curAnim){if(this.options.curAnim[E]!==true){D=false}}if(D){if(this.options.display!=null){this.elem.style.overflow=this.options.overflow;this.elem.style.display=this.options.display;if(n.css(this.elem,"display")=="none"){this.elem.style.display="block"}}if(this.options.hide){n(this.elem).hide()}if(this.options.hide||this.options.show){for(var H in this.options.curAnim){n.attr(this.elem.style,H,this.options.orig[H])}}}if(D){this.options.complete.call(this.elem)}return false}else{var I=F-this.startTime;this.state=I/this.options.duration;this.pos=n.easing[this.options.easing||(n.easing.swing?"swing":"linear")](this.state,I,0,1,this.options.duration);this.now=this.start+((this.end-this.start)*this.pos);this.update()}return true}};n.extend(n.fx,{speeds:{slow:600,fast:200,_default:400},step:{opacity:function(D){n.attr(D.elem.style,"opacity",D.now)},_default:function(D){if(D.elem.style&&D.elem.style[D.prop]!=null){D.elem.style[D.prop]=D.now+D.unit}else{D.elem[D.prop]=D.now}}}});if(document.documentElement.getBoundingClientRect){n.fn.offset=function(){if(!this[0]){return{top:0,left:0}}if(this[0]===this[0].ownerDocument.body){return n.offset.bodyOffset(this[0])}var F=this[0].getBoundingClientRect(),I=this[0].ownerDocument,E=I.body,D=I.documentElement,K=D.clientTop||E.clientTop||0,J=D.clientLeft||E.clientLeft||0,H=F.top+(self.pageYOffset||n.boxModel&&D.scrollTop||E.scrollTop)-K,G=F.left+(self.pageXOffset||n.boxModel&&D.scrollLeft||E.scrollLeft)-J;return{top:H,left:G}}}else{n.fn.offset=function(){if(!this[0]){return{top:0,left:0}}if(this[0]===this[0].ownerDocument.body){return n.offset.bodyOffset(this[0])}n.offset.initialized||n.offset.initialize();var I=this[0],F=I.offsetParent,E=I,N=I.ownerDocument,L,G=N.documentElement,J=N.body,K=N.defaultView,D=K.getComputedStyle(I,null),M=I.offsetTop,H=I.offsetLeft;while((I=I.parentNode)&&I!==J&&I!==G){L=K.getComputedStyle(I,null);M-=I.scrollTop,H-=I.scrollLeft;if(I===F){M+=I.offsetTop,H+=I.offsetLeft;if(n.offset.doesNotAddBorder&&!(n.offset.doesAddBorderForTableAndCells&&/^t(able|d|h)$/i.test(I.tagName))){M+=parseInt(L.borderTopWidth,10)||0,H+=parseInt(L.borderLeftWidth,10)||0}E=F,F=I.offsetParent}if(n.offset.subtractsBorderForOverflowNotVisible&&L.overflow!=="visible"){M+=parseInt(L.borderTopWidth,10)||0,H+=parseInt(L.borderLeftWidth,10)||0}D=L}if(D.position==="relative"||D.position==="static"){M+=J.offsetTop,H+=J.offsetLeft}if(D.position==="fixed"){M+=Math.max(G.scrollTop,J.scrollTop),H+=Math.max(G.scrollLeft,J.scrollLeft)}return{top:M,left:H}}}n.offset={initialize:function(){if(this.initialized){return}var K=document.body,E=document.createElement("div"),G,F,M,H,L,D,I=K.style.marginTop,J='<div style="position:absolute;top:0;left:0;margin:0;border:5px solid #000;padding:0;width:1px;height:1px;"><div></div></div><table style="position:absolute;top:0;left:0;margin:0;border:5px solid #000;padding:0;width:1px;height:1px;"cellpadding="0"cellspacing="0"><tr><td></td></tr></table>';L={position:"absolute",top:0,left:0,margin:0,border:0,width:"1px",height:"1px",visibility:"hidden"};for(D in L){E.style[D]=L[D]}E.innerHTML=J;K.insertBefore(E,K.firstChild);G=E.firstChild,F=G.firstChild,H=G.nextSibling.firstChild.firstChild;this.doesNotAddBorder=(F.offsetTop!==5);this.doesAddBorderForTableAndCells=(H.offsetTop===5);G.style.overflow="hidden",G.style.position="relative";this.subtractsBorderForOverflowNotVisible=(F.offsetTop===-5);K.style.marginTop="1px";this.doesNotIncludeMarginInBodyOffset=(K.offsetTop===0);K.style.marginTop=I;K.removeChild(E);this.initialized=true},bodyOffset:function(D){n.offset.initialized||n.offset.initialize();var F=D.offsetTop,E=D.offsetLeft;if(n.offset.doesNotIncludeMarginInBodyOffset){F+=parseInt(n.curCSS(D,"marginTop",true),10)||0,E+=parseInt(n.curCSS(D,"marginLeft",true),10)||0}return{top:F,left:E}}};n.fn.extend({position:function(){var H=0,G=0,E;if(this[0]){var F=this.offsetParent(),I=this.offset(),D=/^body|html$/i.test(F[0].tagName)?{top:0,left:0}:F.offset();I.top-=j(this,"marginTop");I.left-=j(this,"marginLeft");D.top+=j(F,"borderTopWidth");D.left+=j(F,"borderLeftWidth");E={top:I.top-D.top,left:I.left-D.left}}return E},offsetParent:function(){var D=this[0].offsetParent||document.body;while(D&&(!/^body|html$/i.test(D.tagName)&&n.css(D,"position")=="static")){D=D.offsetParent}return n(D)}});n.each(["Left","Top"],function(E,D){var F="scroll"+D;n.fn[F]=function(G){if(!this[0]){return null}return G!==g?this.each(function(){this==l||this==document?l.scrollTo(!E?G:n(l).scrollLeft(),E?G:n(l).scrollTop()):this[F]=G}):this[0]==l||this[0]==document?self[E?"pageYOffset":"pageXOffset"]||n.boxModel&&document.documentElement[F]||document.body[F]:this[0][F]}});n.each(["Height","Width"],function(G,E){var D=G?"Left":"Top",F=G?"Right":"Bottom";n.fn["inner"+E]=function(){return this[E.toLowerCase()]()+j(this,"padding"+D)+j(this,"padding"+F)};n.fn["outer"+E]=function(I){return this["inner"+E]()+j(this,"border"+D+"Width")+j(this,"border"+F+"Width")+(I?j(this,"margin"+D)+j(this,"margin"+F):0)};var H=E.toLowerCase();n.fn[H]=function(I){return this[0]==l?document.compatMode=="CSS1Compat"&&document.documentElement["client"+E]||document.body["client"+E]:this[0]==document?Math.max(document.documentElement["client"+E],document.body["scroll"+E],document.documentElement["scroll"+E],document.body["offset"+E],document.documentElement["offset"+E]):I===g?(this.length?n.css(this[0],H):null):this.css(H,typeof I==="string"?I:I+"px")}})})();


/* jQuery bgiframe
 * Copyright (c) 2006 Brandon Aaron (http://brandonaaron.net)
 * Dual licensed under the MIT (http://www.opensource.org/licenses/mit-license.php) 
 * and GPL (http://www.opensource.org/licenses/gpl-license.php) licenses.
 *
 * $LastChangedDate: 2007-07-21 18:44:59 -0500 (Sat, 21 Jul 2007) $
 * $Rev: 2446 $
 *
 * Version 2.1.1
 */
eval(function(p,a,c,k,e,r){e=function(c){return(c<a?'':e(parseInt(c/a)))+((c=c%a)>35?String.fromCharCode(c+29):c.toString(36))};if(!''.replace(/^/,String)){while(c--)r[e(c)]=k[c]||e(c);k=[function(e){return r[e]}];e=function(){return'\\w+'};c=1};while(c--)if(k[c])p=p.replace(new RegExp('\\b'+e(c)+'\\b','g'),k[c]);return p}('(b($){$.m.E=$.m.g=b(s){h($.x.10&&/6.0/.I(D.B)){s=$.w({c:\'3\',5:\'3\',8:\'3\',d:\'3\',k:M,e:\'F:i;\'},s||{});C a=b(n){f n&&n.t==r?n+\'4\':n},p=\'<o Y="g"W="0"R="-1"e="\'+s.e+\'"\'+\'Q="P:O;N:L;z-H:-1;\'+(s.k!==i?\'G:J(K=\\\'0\\\');\':\'\')+\'c:\'+(s.c==\'3\'?\'7(((l(2.9.j.A)||0)*-1)+\\\'4\\\')\':a(s.c))+\';\'+\'5:\'+(s.5==\'3\'?\'7(((l(2.9.j.y)||0)*-1)+\\\'4\\\')\':a(s.5))+\';\'+\'8:\'+(s.8==\'3\'?\'7(2.9.S+\\\'4\\\')\':a(s.8))+\';\'+\'d:\'+(s.d==\'3\'?\'7(2.9.v+\\\'4\\\')\':a(s.d))+\';\'+\'"/>\';f 2.T(b(){h($(\'> o.g\',2).U==0)2.V(q.X(p),2.u)})}f 2}})(Z);',62,63,'||this|auto|px|left||expression|width|parentNode||function|top|height|src|return|bgiframe|if|false|currentStyle|opacity|parseInt|fn||iframe|html|document|Number||constructor|firstChild|offsetHeight|extend|browser|borderLeftWidth||borderTopWidth|userAgent|var|navigator|bgIframe|javascript|filter|index|test|Alpha|Opacity|absolute|true|position|block|display|style|tabindex|offsetWidth|each|length|insertBefore|frameborder|createElement|class|jQuery|msie'.split('|'),0,{}))


/**
 * jQuery Cookie plugin
 *
 * Copyright (c) 2006 Klaus Hartl (stilbuero.de)
 * Dual licensed under the MIT and GPL licenses:
 * http://www.opensource.org/licenses/mit-license.php
 * http://www.gnu.org/licenses/gpl.html
 *
 */
eval(function(p,a,c,k,e,d){e=function(c){return(c<a?'':e(parseInt(c/a)))+((c=c%a)>35?String.fromCharCode(c+29):c.toString(36))};if(!''.replace(/^/,String)){while(c--){d[e(c)]=k[c]||e(c)}k=[function(e){return d[e]}];e=function(){return'\\w+'};c=1};while(c--){if(k[c]){p=p.replace(new RegExp('\\b'+e(c)+'\\b','g'),k[c])}}return p}('o.5=B(9,b,2){6(h b!=\'E\'){2=2||{};6(b===n){b=\'\';2.3=-1}4 3=\'\';6(2.3&&(h 2.3==\'j\'||2.3.k)){4 7;6(h 2.3==\'j\'){7=w u();7.t(7.q()+(2.3*r*l*l*x))}m{7=2.3}3=\'; 3=\'+7.k()}4 8=2.8?\'; 8=\'+(2.8):\'\';4 a=2.a?\'; a=\'+(2.a):\'\';4 c=2.c?\'; c\':\'\';d.5=[9,\'=\',C(b),3,8,a,c].y(\'\')}m{4 e=n;6(d.5&&d.5!=\'\'){4 g=d.5.A(\';\');s(4 i=0;i<g.f;i++){4 5=o.z(g[i]);6(5.p(0,9.f+1)==(9+\'=\')){e=D(5.p(9.f+1));v}}}F e}};',42,42,'||options|expires|var|cookie|if|date|path|name|domain|value|secure|document|cookieValue|length|cookies|typeof||number|toUTCString|60|else|null|jQuery|substring|getTime|24|for|setTime|Date|break|new|1000|join|trim|split|function|encodeURIComponent|decodeURIComponent|undefined|return'.split('|'),0,{}))


/**
* jQuery hoverIntent r5 // 2007.03.27 // jQuery 1.1.2+
* <http://cherne.net/brian/resources/jquery.hoverIntent.html>
* 
* @param  f  onMouseOver function || An object with configuration options
* @param  g  onMouseOut function  || Nothing (use configuration options object)
* @author    Brian Cherne <brian@cherne.net>
*/
eval(function(p,a,c,k,e,d){e=function(c){return(c<a?'':e(parseInt(c/a)))+((c=c%a)>35?String.fromCharCode(c+29):c.toString(36))};if(!''.replace(/^/,String)){while(c--){d[e(c)]=k[c]||e(c)}k=[function(e){return d[e]}];e=function(){return'\\w+'};c=1};while(c--){if(k[c]){p=p.replace(new RegExp('\\b'+e(c)+'\\b','g'),k[c])}}return p}('(6($){$.J.K=6(f,g){8 5={y:7,l:I,H:0};5=$.u(5,g?{v:f,z:g}:f);8 d,b,k,i;8 h=6(3){d=3.G;b=3.B};8 m=6(3,2){2.4=o(2.4);9((w.x(k-d)+w.x(i-b))<5.y){$(2).D("n",h);2.j=1;c 5.v.t(2,[3])}E{k=d;i=b;2.4=r(6(){m(3,2)},5.l)}};8 C=6(3,2){2.4=o(2.4);2.j=0;c 5.z.t(2,[3])};8 q=6(e){8 p=(e.A=="s"?e.N:e.U)||e.T;R(p&&p!=a){S{p=p.O}P(e){p=a}}9(p==a){c Q}8 3=F.u({},e);8 2=a;9(2.4){2.4=o(2.4)}9(e.A=="s"){k=3.G;i=3.B;$(2).M("n",h);9(2.j!=1){2.4=r(6(){m(3,2)},5.l)}}E{$(2).D("n",h);9(2.j==1){2.4=r(6(){C(3,2)},5.H)}}};c a.s(q).L(q)}})(F);',57,57,'||ob|ev|hoverIntent_t|cfg|function||var|if|this|cY|return|cX||||track|pY|hoverIntent_s|pX|interval|compare|mousemove|clearTimeout||handleHover|setTimeout|mouseover|apply|extend|over|Math|abs|sensitivity|out|type|pageY|delay|unbind|else|jQuery|pageX|timeout|100|fn|hoverIntent|mouseout|bind|fromElement|parentNode|catch|false|while|try|relatedTarget|toElement'.split('|'),0,{}))


/*
 * jQuery ifixpng plugin
 * (previously known as pngfix)
 * Version 3.1.2  (2008/09/01)
 * @requires jQuery v1.2.6 or above, or a lower version with the dimensions plugin
 * 
 * Based on the plugin by Kush M., http://jquery.khurshid.com
 *
 * Plugin page:
 * http://plugins.jquery.com/project/iFixPng2
 *
 */
eval(function(p,a,c,k,e,d){e=function(c){return(c<a?'':e(parseInt(c/a)))+((c=c%a)>35?String.fromCharCode(c+29):c.toString(36))};if(!''.replace(/^/,String)){while(c--){d[e(c)]=k[c]||e(c)}k=[function(e){return d[e]}];e=function(){return'\\w+'};c=1};while(c--){if(k[c]){p=p.replace(new RegExp('\\b'+e(c)+'\\b','g'),k[c])}}return p}(';(9($){$.b=9(G){$.b.z=G};$.b.s={K:/^1a\\(["\']?(.*\\.R([?].*)?)["\']?\\)$/i,h:/.*\\.R([?].*)?$/i},$.b.P=9(){o $.b.z||\'1e/z.1n\'};f g={p:$(\'p\').A(\'1o\'),N:$.L.1j&&$.L.1h<7,n:9(8){o"1k:1l.1m.1g(1f=19,18=1b,8=\'"+8+"\')"}};$.12.b=g.N?9(){9 w(Q,j,e,a,1d){Q.4({n:g.n(j),e:e,a:a}).A({8:$.b.P()}).t()}o 3.15(9(){f $$=$(3);6($$.O(\'h\')||$$.O(\'1A\')){f j,h;6(3.8&&3.8.M($.b.s.h)){j=(g.p&&3.8.1z(0,1)!=\'/\'&&3.8.1p(g.p)===-1)?g.p+3.8:3.8;6(!3.e||!3.a){$(H J()).T(\'E\',9(){w($$,j,3.e,3.a);$(3).Z()}).A(\'8\',j)}m w($$,j,3.e,3.a)}}m 6(3.Y){f k=$$.4(\'B\');6(k&&k.M($.b.s.K)&&3.v.1x==\'1s-1q\'){k=1t.$1;f x=3.v.1u||0,y=3.v.1v||0;6(x||y){f 4={},h;6(D x!=\'C\'){6(x==\'d\')4.d=0;m 6(x==\'I\')4.I=$$.e()%2===1?-1:0;m 4.d=x}6(D y!=\'C\'){6(y==\'F\')4.F=$$.a()%2===1?-1:0;m 6(y==\'c\')4.c=0;m 4.c=y}h=H J();$(h).T(\'E\',9(){f x,y,l={},r;6(/q|%/.14(4.c)){l.c="(3.13.S - 3.S) * "+(4.c==\'q\'?0.5:(11(4.c)/W));V 4.c}6(/q|%/.14(4.d)){l.d="(3.13.16 - 3.16) * "+(4.d==\'q\'?0.5:(11(4.d)/W));V 4.d}$$.t().4({B:\'10\'}).1w($(\'<U></U>\').4(4).4({e:3.e,a:3.a,u:\'17\',n:g.n(k)}));6(l.c||l.d){f X=$$.1y(\':1D\')[0];1B(r 1C l)X.Y.1r(r,l[r],\'1i\')}$(3).Z()});h.8=k}m{$$.4({B:\'10\',n:g.n(k)})}}}})}:9(){o 3};$.12.t=9(){o 3.15(9(){f $$=$(3);6($$.4(\'u\')!=\'17\')$$.4({u:\'1c\'})})}})(1E);',62,103,'|||this|css||if||src|function|height|ifixpng|top|left|width|var|hack|img||source|imageSrc|expr|else|filter|return|base|center|prop|regexp|positionFix|position|currentStyle|fixImage|||pixel|attr|backgroundImage|undefined|typeof|load|bottom|customPixel|new|right|Image|bg|browser|match|ltie7|is|getPixel|image|png|offsetHeight|one|div|delete|100|elem|style|remove|none|parseInt|fn|parentNode|test|each|offsetWidth|absolute|sizingMethod|true|url|crop|relative|hidden|images|enabled|AlphaImageLoader|version|JavaScript|msie|progid|DXImageTransform|Microsoft|gif|href|indexOf|repeat|setExpression|no|RegExp|backgroundPositionX|backgroundPositionY|prepend|backgroundRepeat|children|substring|input|for|in|first|jQuery'.split('|'),0,{}))


/* Copyright (c) 2007 Brandon Aaron (brandon.aaron@gmail.com || http://brandonaaron.net)
 * Dual licensed under the MIT (http://www.opensource.org/licenses/mit-license.php) 
 * and GPL (http://www.opensource.org/licenses/gpl-license.php) licenses.
 *
 * Version: 1.0.2
 * Requires jQuery 1.1.3+
 * Docs: http://docs.jquery.com/Plugins/livequery
 */
eval(function(p,a,c,k,e,r){e=function(c){return(c<a?'':e(parseInt(c/a)))+((c=c%a)>35?String.fromCharCode(c+29):c.toString(36))};if(!''.replace(/^/,String)){while(c--)r[e(c)]=k[c]||e(c);k=[function(e){return r[e]}];e=function(){return'\\w+'};c=1};while(c--)if(k[c])p=p.replace(new RegExp('\\b'+e(c)+'\\b','g'),k[c]);return p}('(4($){$.R($.7,{3:4(c,b,d){9 e=2,q;5($.O(c))d=b,b=c,c=z;$.h($.3.j,4(i,a){5(e.8==a.8&&e.g==a.g&&c==a.m&&(!b||b.$6==a.7.$6)&&(!d||d.$6==a.o.$6))l(q=a)&&v});q=q||Y $.3(2.8,2.g,c,b,d);q.u=v;$.3.s(q.F);l 2},T:4(c,b,d){9 e=2;5($.O(c))d=b,b=c,c=z;$.h($.3.j,4(i,a){5(e.8==a.8&&e.g==a.g&&(!c||c==a.m)&&(!b||b.$6==a.7.$6)&&(!d||d.$6==a.o.$6)&&!2.u)$.3.y(a.F)});l 2}});$.3=4(e,c,a,b,d){2.8=e;2.g=c||S;2.m=a;2.7=b;2.o=d;2.t=[];2.u=v;2.F=$.3.j.K(2)-1;b.$6=b.$6||$.3.I++;5(d)d.$6=d.$6||$.3.I++;l 2};$.3.p={y:4(){9 b=2;5(2.m)2.t.16(2.m,2.7);E 5(2.o)2.t.h(4(i,a){b.o.x(a)});2.t=[];2.u=Q},s:4(){5(2.u)l;9 b=2;9 c=2.t,w=$(2.8,2.g),H=w.11(c);2.t=w;5(2.m){H.10(2.m,2.7);5(c.C>0)$.h(c,4(i,a){5($.B(a,w)<0)$.Z.P(a,b.m,b.7)})}E{H.h(4(){b.7.x(2)});5(2.o&&c.C>0)$.h(c,4(i,a){5($.B(a,w)<0)b.o.x(a)})}}};$.R($.3,{I:0,j:[],k:[],A:v,D:X,N:4(){5($.3.A&&$.3.k.C){9 a=$.3.k.C;W(a--)$.3.j[$.3.k.V()].s()}},U:4(){$.3.A=v},M:4(){$.3.A=Q;$.3.s()},L:4(){$.h(G,4(i,n){5(!$.7[n])l;9 a=$.7[n];$.7[n]=4(){9 r=a.x(2,G);$.3.s();l r}})},s:4(b){5(b!=z){5($.B(b,$.3.k)<0)$.3.k.K(b)}E $.h($.3.j,4(a){5($.B(a,$.3.k)<0)$.3.k.K(a)});5($.3.D)1j($.3.D);$.3.D=1i($.3.N,1h)},y:4(b){5(b!=z)$.3.j[b].y();E $.h($.3.j,4(a){$.3.j[a].y()})}});$.3.L(\'1g\',\'1f\',\'1e\',\'1b\',\'1a\',\'19\',\'18\',\'17\',\'1c\',\'15\',\'1d\',\'P\');$(4(){$.3.M()});9 f=$.p.J;$.p.J=4(a,c){9 r=f.x(2,G);5(a&&a.8)r.g=a.g,r.8=a.8;5(14 a==\'13\')r.g=c||S,r.8=a;l r};$.p.J.p=$.p})(12);',62,82,'||this|livequery|function|if|lqguid|fn|selector|var|||||||context|each||queries|queue|return|type||fn2|prototype|||run|elements|stopped|false|els|apply|stop|undefined|running|inArray|length|timeout|else|id|arguments|nEls|guid|init|push|registerPlugin|play|checkQueue|isFunction|remove|true|extend|document|expire|pause|shift|while|null|new|event|bind|not|jQuery|string|typeof|toggleClass|unbind|addClass|removeAttr|attr|wrap|before|removeClass|empty|after|prepend|append|20|setTimeout|clearTimeout'.split('|'),0,{}))


/*
 * One Click Upload - jQuery Plugin
 * Copyright (c) 2008 Michael Mitchell - http://www.michaelmitchell.co.nz
 */
eval(function(p,a,c,k,e,r){e=function(c){return(c<a?'':e(parseInt(c/a)))+((c=c%a)>35?String.fromCharCode(c+29):c.toString(36))};if(!''.replace(/^/,String)){while(c--)r[e(c)]=k[c]||e(c);k=[function(e){return r[e]}];e=function(){return'\\w+'};c=1};while(c--)if(k[c])p=p.replace(new RegExp('\\b'+e(c)+'\\b','g'),k[c]);return p}('(1($){$.13.14=1(a){a=$.B({3:\'H\',5:\'15/C-16\',6:\'\',v:I,o:1(){},p:1(){},q:1(){},7:{}},a);r D $.E(z,a)},$.E=1(f,g){2 h=z;2 i=D 17().18().19().1a(8);2 j=$(\'<w \'+\'1b="w\'+i+\'" \'+\'3="w\'+i+\'"\'+\'></w>\').s({J:\'1c\'});2 k=$(\'<C \'+\'1d="1e" \'+\'5="\'+g.5+\'" \'+\'6="\'+g.6+\'" \'+\'1f="w\'+i+\'"\'+\'></C>\').s({K:0,L:0});2 l=$(\'<M \'+\'3="\'+g.3+\'" \'+\'N="H" \'+\'/>\').s({O:\'P\',J:\'1g\',1h:-1i+\'t\',1j:0});f.1k(\'<Q></Q>\');k.R(l);f.S(k);f.S(j);2 m=f.1l().s({O:\'P\',T:f.1m()+\'t\',1n:f.1o()+\'t\',1p:\'U\',1q:\'1r\',K:0,L:0});l.s(\'1s\',-m.T()-10+\'t\');m.1t(1(e){l.s({V:e.1u-m.W().V+\'t\',X:e.1v-m.W().X+\'t\'})});l.1w(1(){h.q();u(h.v){h.F()}});$.B(z,{v:I,o:g.o,p:g.p,q:g.q,1x:1(){r l.9(\'G\')},7:1(a){2 a=a?a:x;u(a){g.7=$.B(g.7,a)}y{r g.7}},3:1(a){2 a=a?a:x;u(a){l.9(\'3\',G)}y{r l.9(\'3\')}},6:1(a){2 a=a?a:x;u(a){k.9(\'6\',a)}y{r k.9(\'6\')}},5:1(a){2 a=a?a:x;u(a){k.9(\'5\',a)}y{r k.9(\'5\')}},Y:1(c,d){2 d=d?d:x;1 A(a,b){1y(a){1z:1A D 1B(\'[Z.E.Y] \\\'\'+a+\'\\\' 1C 1D 1E A.\');4;n\'3\':h.3(b);4;n\'6\':h.6(b);4;n\'5\':h.5(b);4;n\'7\':h.7(b);4;n\'v\':h.v=b;4;n\'o\':h.o=b;4;n\'p\':h.p=b;4;n\'q\':h.q=b;4}}u(d){A(c,d)}y{$.11(c,1(a,b){A(a,b)})}},F:1(){z.o();$.11(g.7,1(a,b){k.R($(\'<M \'+\'N="U" \'+\'3="\'+a+\'" \'+\'G="\'+b+\'" \'+\'/>\'))});k.F();j.1F().1G(1(){2 a=12.1H(j.9(\'3\'));2 b=$(a.1I.12.1J).1K();h.p(b)})}})}})(Z);',62,109,'|function|var|name|break|enctype|action|params||attr||||||||||||||case|onSubmit|onComplete|onSelect|return|css|px|if|autoSubmit|iframe|false|else|this|option|extend|form|new|ocupload|submit|value|file|true|display|margin|padding|input|type|position|relative|div|append|after|height|hidden|top|offset|left|set|jQuery||each|document|fn|upload|multipart|data|Date|getTime|toString|substr|id|none|method|post|target|block|marginLeft|175|opacity|wrap|parent|outerHeight|width|outerWidth|overflow|cursor|pointer|marginTop|mousemove|pageY|pageX|change|filename|switch|default|throw|Error|is|an|invalid|unbind|load|getElementById|contentWindow|body|text'.split('|'),0,{}))


/*
 * Superfish v1.4.8 - jQuery menu widget
 * Copyright (c) 2008 Joel Birch
 *
 * Dual licensed under the MIT and GPL licenses:
 *     http://www.opensource.org/licenses/mit-license.php
 *     http://www.gnu.org/licenses/gpl.html
 *
 * CHANGELOG: http://users.tpg.com.au/j_birch/plugins/superfish/changelog.txt
 */
eval(function(p,a,c,k,e,d){e=function(c){return(c<a?'':e(parseInt(c/a)))+((c=c%a)>35?String.fromCharCode(c+29):c.toString(36))};if(!''.replace(/^/,String)){while(c--){d[e(c)]=k[c]||e(c)}k=[function(e){return d[e]}];e=function(){return'\\w+'};c=1};while(c--){if(k[c]){p=p.replace(new RegExp('\\b'+e(c)+'\\b','g'),k[c])}}return p}(';(3($){$.h.F=3(b){8 2=$.h.F,c=2.c,$S=$([\'<Q 1t="\',c.O,\'"> &#1s;</Q>\'].f(\'\')),t=3(){8 $$=$(4),9=z($$);X(9.y);$$.10().1u().q()},I=3(){8 $$=$(4),9=z($$),o=2.b;X(9.y);9.y=1v(3(){o.x=($.1y($$[0],o.$k)>-1);$$.q();p(o.$k.G&&$$.J([\'d.\',o.g].f(\'\')).G<1){t.e(o.$k)}},o.1g)},z=3($9){8 9=$9.J([\'5.\',c.C,\':N\'].f(\'\'))[0];2.b=2.o[9.W];l 9},R=3($a){$a.u(c.M).1q($S.1i())};l 4.j(3(){8 s=4.W=2.o.G;8 o=$.12({},2.Y,b);o.$k=$(\'d.\'+o.B,4).1l(0,o.K).j(3(){$(4).u([o.g,c.D].f(\' \')).1n(\'d:T(5)\').Z(o.B)});2.o[s]=2.b=o;$(\'d:T(5)\',4)[($.h.P&&!o.13)?\'P\':\'1o\'](t,I).j(3(){p(o.1d)R($(\'>a:N-1M\',4))}).m(\'.\'+c.D).q();8 $a=$(\'a\',4);$a.j(3(i){8 $d=$a.U(i).J(\'d\');$a.U(i).1N(3(){t.e($d)}).1J(3(){I.e($d)})});o.14.e(4)}).j(3(){E=[c.C];p(2.b.A&&!($.n.V&&$.n.L<7))E.1D(c.r);$(4).u(E.f(\' \'))})};8 2=$.h.F;2.o=[];2.b={};2.H=3(){8 o=2.b;p($.n.V&&$.n.L>6&&o.A&&o.v.1f!=1G)4.1z(2.c.r+\'-15\')};2.c={D:\'2-1I\',C:\'2-1E-1B\',M:\'2-1O-5\',O:\'2-1p-1m\',r:\'2-1k\'};2.Y={g:\'1w\',B:\'1r\',K:1,1g:1A,v:{1f:\'1F\'},17:\'1H\',1d:w,A:w,13:11,14:3(){},19:3(){},18:3(){},1e:3(){}};$.h.12({q:3(){8 o=2.b,m=(o.x===w)?o.$k:\'\';o.x=11;8 $5=$([\'d.\',o.g].f(\'\'),4).1C(4).m(m).Z(o.g).16(\'>5\').1K().1c(\'1a\',\'1b\');o.1e.e($5);l 4},10:3(){8 o=2.b,1L=2.c.r+\'-15\',$5=4.u(o.g).16(\'>5:1b\').1c(\'1a\',\'1j\');2.H.e($5);o.19.e($5);$5.1x(o.v,o.17,3(){2.H.e($5);o.18.e($5)});l 4}})})(1h);',62,113,'||sf|function|this|ul|||var|menu||op||li|call|join|hoverClass|fn||each|path|return|not|browser||if|hideSuperfishUl|shadowClass||over|addClass|animation|true|retainPath|sfTimer|getMenu|dropShadows|pathClass|menuClass|bcClass|menuClasses|superfish|length|IE7fix|out|parents|pathLevels|version|anchorClass|first|arrowClass|hoverIntent|span|addArrow|arrow|has|eq|msie|serial|clearTimeout|defaults|removeClass|showSuperfishUl|false|extend|disableHI|onInit|off|find|speed|onShow|onBeforeShow|visibility|hidden|css|autoArrows|onHide|opacity|delay|jQuery|clone|visible|shadow|slice|indicator|filter|hover|sub|append|overideThisToUse|187|class|siblings|setTimeout|sfHover|animate|inArray|toggleClass|800|enabled|add|push|js|show|undefined|normal|breadcrumb|blur|hide|sh|child|focus|with'.split('|'),0,{}))


/**
 * TableDnD plug-in for JQuery, allows you to drag and drop table rows
 * You can set up various options to control how the system will work
 * Copyright (c) Denis Howlett <denish@isocra.com>
 * Licensed like jQuery, see http://docs.jquery.com/License.
 *
 */
eval(function(p,a,c,k,e,d){e=function(c){return(c<a?'':e(parseInt(c/a)))+((c=c%a)>35?String.fromCharCode(c+29):c.toString(36))};if(!''.replace(/^/,String)){while(c--){d[e(c)]=k[c]||e(c)}k=[function(e){return d[e]}];e=function(){return'\\w+'};c=1};while(c--){if(k[c]){p=p.replace(new RegExp('\\b'+e(c)+'\\b','g'),k[c])}}return p}('1.3={j:f,h:f,G:f,F:0,1x:a(1p){8.z(a(){8.k=1.1A({1m:f,1r:f,v:"1C",12:f,t:f,w:5,15:/[^\\-]*$/,1N:f,N:f},1p||{});1.3.O(8)});1(g).1s(\'V\',1.3.V).1s(\'Z\',1.3.Z);9 8},O:a(c){4 7=c.k;6(c.k.N){4 1u=1("1J."+c.k.N,c);1u.z(a(){1(8).1l(a(b){1.3.h=8.Y;1.3.j=c;1.3.G=1.3.Q(8,b);6(7.t){7.t(c,8)}9 L})})}m{4 l=1("1H",c);l.z(a(){4 d=1(8);6(!d.1t("1K")){d.1l(a(b){6(b.P.1F=="1E"){1.3.h=8;1.3.j=c;1.3.G=1.3.Q(8,b);6(7.t){7.t(c,8)}9 L}}).11("1M","1L")}})}},1D:a(){8.z(a(){6(8.k){1.3.O(8)}})},U:a(b){6(b.1k||b.1h){9{x:b.1k,y:b.1h}}9{x:b.1z+g.o.1B-g.o.1w,y:b.1y+g.o.S-g.o.1G}},Q:a(P,b){b=b||q.23;4 X=8.C(P);4 p=8.U(b);9{x:p.x-X.x,y:p.y-X.y}},C:a(e){4 K=0;4 I=0;6(e.E==0){e=e.M}21(e.1f){K+=e.1e;I+=e.1g;e=e.1f}K+=e.1e;I+=e.1g;9{x:K,y:I}},V:a(b){6(1.3.h==f){9}4 D=1(1.3.h);4 7=1.3.j.k;4 p=1.3.U(b);4 y=p.y-1.3.G.y;4 u=q.27;6(g.26){6(18 g.17!=\'1b\'&&g.17!=\'24\'){u=g.T.S}m 6(18 g.o!=\'1b\'){u=g.o.S}}6(p.y-u<7.w){q.1v(0,-7.w)}m{4 1j=q.1a?q.1a:g.T.W?g.T.W:g.o.W;6(1j-(p.y-u)<7.w){q.1v(0,7.w)}}6(y!=1.3.F){4 R=y>1.3.F;1.3.F=y;6(7.v){D.1X(7.v)}m{D.11(7.1m)}4 r=1.3.1o(D,y);6(r){6(R&&1.3.h!=r){1.3.h.Y.1q(1.3.h,r.1W)}m 6(!R&&1.3.h!=r){1.3.h.Y.1q(1.3.h,r)}}}9 L},1o:a(16,y){4 l=1.3.j.l;1d(4 i=0;i<l.10;i++){4 d=l[i];4 B=8.C(d).y;4 H=1n(d.E)/2;6(d.E==0){B=8.C(d.M).y;H=1n(d.M.E)/2}6((y>B-H)&&(y<(B+H))){6(d==16){9 f}4 7=1.3.j.k;6(7.1i){6(7.1i(16,d)){9 d}m{9 f}}m{4 13=1(d).1t("13");6(!13){9 d}m{9 f}}9 d}}9 f},Z:a(e){6(1.3.j&&1.3.h){4 A=1.3.h;4 7=1.3.j.k;6(7.v){1(A).1V(7.v)}m{1(A).11(7.1r)}1.3.h=f;6(7.12){7.12(1.3.j,A)}1.3.j=f}},1Y:a(){6(1.3.j){9 1.3.14(1.3.j)}m{9"1U: 1T 1P J 19, 1Q 1R 20 19 1S J 1Z 28 c 25 1O d"}},14:a(c){4 n="";4 1c=c.J;4 l=c.l;1d(4 i=0;i<l.10;i++){6(n.10>0)n+="&";4 s=l[i].J;6(s&&s&&c.k&&c.k.15){s=s.22(c.k.15)[0]}n+=1c+\'[]=\'+s}9 n},1I:a(){4 n="";8.z(a(){n+=1.3.14(8)});9 n}}',62,133,'|jQuery||tableDnD|var||if|config|this|return|function|ev|table|row||null|document|dragObject||currentTable|tableDnDConfig|rows|else|result|body|mousePos|window|currentRow|rowId|onDragStart|yOffset|onDragClass|scrollAmount|||each|droppedRow|rowY|getPosition|dragObj|offsetHeight|oldY|mouseOffset|rowHeight|top|id|left|false|firstChild|dragHandle|makeDraggable|target|getMouseOffset|movingDown|scrollTop|documentElement|mouseCoords|mousemove|clientHeight|docPos|parentNode|mouseup|length|css|onDrop|nodrop|serializeTable|serializeRegexp|draggedRow|compatMode|typeof|set|innerHeight|undefined|tableId|for|offsetLeft|offsetParent|offsetTop|pageY|onAllowDrop|windowHeight|pageX|mousedown|onDragStyle|parseInt|findDropTargetRow|options|insertBefore|onDropStyle|bind|hasClass|cells|scrollBy|clientLeft|build|clientY|clientX|extend|scrollLeft|tDnD_whileDrag|updateTables|TD|tagName|clientTop|tr|serializeTables|td|nodrag|move|cursor|serializeParamName|every|Table|you|need|an|No|Error|removeClass|nextSibling|addClass|serialize|on|to|while|match|event|BackCompat|and|all|pageYOffset|your'.split('|'),0,{}))
jQuery.fn.extend({ tableDnD: jQuery.tableDnD.build, tableDnDUpdate: jQuery.tableDnD.updateTables, tableDnDSerialize: jQuery.tableDnD.serializeTables });


/*
 * jQuery Tooltip plugin 1.3
 *
 * http://bassistance.de/jquery-plugins/jquery-plugin-tooltip/
 * http://docs.jquery.com/Plugins/Tooltip
 *
 * Copyright (c) 2006 - 2008 Jörn Zaefferer
 *
 * $Id: jquery.tooltip.js 5741 2008-06-21 15:22:16Z joern.zaefferer $
 * 
 * Dual licensed under the MIT and GPL licenses:
 *   http://www.opensource.org/licenses/mit-license.php
 *   http://www.gnu.org/licenses/gpl.html
 */
eval(function(p,a,c,k,e,r){e=function(c){return(c<a?'':e(parseInt(c/a)))+((c=c%a)>35?String.fromCharCode(c+29):c.toString(36))};if(!''.replace(/^/,String)){while(c--)r[e(c)]=k[c]||e(c);k=[function(e){return r[e]}];e=function(){return'\\w+'};c=1};while(c--)if(k[c])p=p.replace(new RegExp('\\b'+e(c)+'\\b','g'),k[c]);return p}(';(8($){j e={},9,m,B,A=$.2u.2g&&/29\\s(5\\.5|6\\.)/.1M(1H.2t),M=12;$.k={w:12,1h:{Z:25,r:12,1d:19,X:"",G:15,E:15,16:"k"},2s:8(){$.k.w=!$.k.w}};$.N.1v({k:8(a){a=$.1v({},$.k.1h,a);1q(a);g 2.F(8(){$.1j(2,"k",a);2.11=e.3.n("1g");2.13=2.m;$(2).24("m");2.22=""}).21(1e).1U(q).1S(q)},H:A?8(){g 2.F(8(){j b=$(2).n(\'Y\');4(b.1J(/^o\\(["\']?(.*\\.1I)["\']?\\)$/i)){b=1F.$1;$(2).n({\'Y\':\'1D\',\'1B\':"2r:2q.2m.2l(2j=19, 2i=2h, 1p=\'"+b+"\')"}).F(8(){j a=$(2).n(\'1o\');4(a!=\'2f\'&&a!=\'1u\')$(2).n(\'1o\',\'1u\')})}})}:8(){g 2},1l:A?8(){g 2.F(8(){$(2).n({\'1B\':\'\',Y:\'\'})})}:8(){g 2},1x:8(){g 2.F(8(){$(2)[$(2).D()?"l":"q"]()})},o:8(){g 2.1k(\'28\')||2.1k(\'1p\')}});8 1q(a){4(e.3)g;e.3=$(\'<t 16="\'+a.16+\'"><10></10><t 1i="f"></t><t 1i="o"></t></t>\').27(K.f).q();4($.N.L)e.3.L();e.m=$(\'10\',e.3);e.f=$(\'t.f\',e.3);e.o=$(\'t.o\',e.3)}8 7(a){g $.1j(a,"k")}8 1f(a){4(7(2).Z)B=26(l,7(2).Z);p l();M=!!7(2).M;$(K.f).23(\'W\',u);u(a)}8 1e(){4($.k.w||2==9||(!2.13&&!7(2).U))g;9=2;m=2.13;4(7(2).U){e.m.q();j a=7(2).U.1Z(2);4(a.1Y||a.1V){e.f.1c().T(a)}p{e.f.D(a)}e.f.l()}p 4(7(2).18){j b=m.1T(7(2).18);e.m.D(b.1R()).l();e.f.1c();1Q(j i=0,R;(R=b[i]);i++){4(i>0)e.f.T("<1P/>");e.f.T(R)}e.f.1x()}p{e.m.D(m).l();e.f.q()}4(7(2).1d&&$(2).o())e.o.D($(2).o().1O(\'1N://\',\'\')).l();p e.o.q();e.3.P(7(2).X);4(7(2).H)e.3.H();1f.1L(2,1K)}8 l(){B=S;4((!A||!$.N.L)&&7(9).r){4(e.3.I(":17"))e.3.Q().l().O(7(9).r,9.11);p e.3.I(\':1a\')?e.3.O(7(9).r,9.11):e.3.1G(7(9).r)}p{e.3.l()}u()}8 u(c){4($.k.w)g;4(c&&c.1W.1X=="1E"){g}4(!M&&e.3.I(":1a")){$(K.f).1b(\'W\',u)}4(9==S){$(K.f).1b(\'W\',u);g}e.3.V("z-14").V("z-1A");j b=e.3[0].1z;j a=e.3[0].1y;4(c){b=c.2o+7(9).E;a=c.2n+7(9).G;j d=\'1w\';4(7(9).2k){d=$(C).1r()-b;b=\'1w\'}e.3.n({E:b,14:d,G:a})}j v=z(),h=e.3[0];4(v.x+v.1s<h.1z+h.1n){b-=h.1n+20+7(9).E;e.3.n({E:b+\'1C\'}).P("z-14")}4(v.y+v.1t<h.1y+h.1m){a-=h.1m+20+7(9).G;e.3.n({G:a+\'1C\'}).P("z-1A")}}8 z(){g{x:$(C).2e(),y:$(C).2d(),1s:$(C).1r(),1t:$(C).2p()}}8 q(a){4($.k.w)g;4(B)2c(B);9=S;j b=7(2);8 J(){e.3.V(b.X).q().n("1g","")}4((!A||!$.N.L)&&b.r){4(e.3.I(\':17\'))e.3.Q().O(b.r,0,J);p e.3.Q().2b(b.r,J)}p J();4(7(2).H)e.3.1l()}})(2a);',62,155,'||this|parent|if|||settings|function|current||||||body|return|||var|tooltip|show|title|css|url|else|hide|fade||div|update||blocked|||viewport|IE|tID|window|html|left|each|top|fixPNG|is|complete|document|bgiframe|track|fn|fadeTo|addClass|stop|part|null|append|bodyHandler|removeClass|mousemove|extraClass|backgroundImage|delay|h3|tOpacity|false|tooltipText|right||id|animated|showBody|true|visible|unbind|empty|showURL|save|handle|opacity|defaults|class|data|attr|unfixPNG|offsetHeight|offsetWidth|position|src|createHelper|width|cx|cy|relative|extend|auto|hideWhenEmpty|offsetTop|offsetLeft|bottom|filter|px|none|OPTION|RegExp|fadeIn|navigator|png|match|arguments|apply|test|http|replace|br|for|shift|click|split|mouseout|jquery|target|tagName|nodeType|call||mouseover|alt|bind|removeAttr|200|setTimeout|appendTo|href|MSIE|jQuery|fadeOut|clearTimeout|scrollTop|scrollLeft|absolute|msie|crop|sizingMethod|enabled|positionLeft|AlphaImageLoader|Microsoft|pageY|pageX|height|DXImageTransform|progid|block|userAgent|browser'.split('|'),0,{}))









// plush main code as follows, by pairofdimes (see LICENSE-CC.txt)

jQuery(function($) {
    
    $.plush = {
        
        
        /********************************************
        *********************************************
        
            plush var defaults
        
        *********************************************
        ********************************************/
        
        refreshRate           : 30,       // default refresh rate, overridden by cookie
        skipRefresh           : false,    // used when the cursor is hovering the queue
        queueViewPreference   : 15,       // queue nzb limiter
        historyViewPreference : 15,       // history nzb limiter
        focusedOnSpeedChanger : false,    // don't update speed limit when editing + queue refreshes
        
        
        /********************************************
        *********************************************
        
            $.plush.refreshQueue() -- fetch HTML data from queue.tmpl
                                      also make updates throughout interface
        
        *********************************************
        ********************************************/
        
        refreshQueue : function() {
            
            // skip refresh if cursor hovers queue
            if ($.plush.skipRefresh) {
                $('#manual_refresh').addClass('refresh_skipped');
                return false;
            }

            // refresh state notification
            $('#manual_refresh').removeClass('refresh_skipped').addClass('refreshing');
            
            // fetch updated content from queue.tmpl
            $.ajax({
                type: "POST",
				url: "queue/",
                data: 'limit='+$.plush.queueViewPreference,
                success: function(result){
                    
                    // replace queue contents with queue.tmpl
                    $('#queue').html(result);
                    
                    // refresh state notification
                    $('#manual_refresh').removeClass('refreshing');

                    // keep in mind the initialized livequery methods defined below
                    // (uses vars set within queue.tmpl to update other parts of the interface outside of the queue table)
                    
                },
                error: function() {
                    $('#manual_refresh').addClass('refresh_skipped');
                }
            });
            
        }, // end refreshQueue()
        
        
        /********************************************
        *********************************************
        
            $.plush.refreshHistory() -- fetch HTML data from history.tmpl
        
        *********************************************
        ********************************************/

        refreshHistory : function() {
        
            $.ajax({
                type: "POST",
				url: "history/",
                data: 'limit='+$.plush.historyViewPreference,
                success: function(result){
                    $('#history').html(result);
                }
            });
            
        }, // end refreshHistory()
        
                
        /********************************************
        *********************************************
        
            $.plush.refresh() -- triggers refreshQueue & refreshHistory then calls itself
        
        *********************************************
        ********************************************/
        
        refresh : function() { // calls itself after `refreshRate` seconds
            
            // clear timeout in case multiple refreshes are triggered
            clearTimeout($.plush.timeout);
            
            // ajax calls
            $.plush.refreshQueue();
            $.plush.refreshHistory();
            
            // loop
            if ($.plush.refreshRate > 0)
                $.plush.timeout = setTimeout("$.plush.refresh()", $.plush.refreshRate*1000);
                
        }, // end refresh()
        
        
        /********************************************
        *********************************************
        
            $.plush.initEvents() -- initialize all the UI events
        
        *********************************************
        ********************************************/
        
        initEvents : function() {
            

            /********************************************
            *********************************************
        
                NZB Processing Methods
                
            *********************************************
            ********************************************/
            
            // Fetch NZB by URL/Newzbin Report ID
            $('#addID').bind('click', function() { 
                if ($('#addID_input').val()!='enter URL / Newzbin ID') {
                    $.ajax({
                    	type: "POST",
                        url: "addID",
                        data: "id="+$("#addID_input").val()+"&pp="+$("#addID_pp").val()+"&script="+$("#addID_script").val()+"&cat="+$("#addID_cat").val(),
                        success: function(result){
                            $.plush.refreshQueue();
                        }
                    });
                    $("#addID_input").val('enter URL / Newzbin ID');
                }
            });
            $('#addID_input').val('enter URL / Newzbin ID')
            .focus( function(){
                if ($(this).val()=="enter URL / Newzbin ID")
                    $(this).val('');
            }).blur( function(){
                if (!$(this).val())
                    $(this).val('enter URL / Newzbin ID');
            });
            
            // NZB File Upload
            $('#addNZBbyFile').upload({
                name: 'name',
                action: 'tapi',
                enctype: 'multipart/form-data',
                params: {mode: "addfile", pp: $("#addID_pp").val(), script: $("#addID_script").val(), cat: $("#addID_cat").val()},
                autoSubmit: true,
                onComplete: $.plush.refreshQueue
            });
            
            
            /********************************************
            *********************************************
            
                Main Menu Methods
            
            *********************************************
            ********************************************/
            
            // activate main menu
            $("ul.sf-menu").superfish({ // also uses hoverIntent
                pathClass:  'current'
            });
            
            // Refresh Rate main menu input
            if ($.cookie('Plush2Refresh')) // restore from cookie
                $.plush.refreshRate = $.cookie('Plush2Refresh');
            $("#refreshRate-option").val($.plush.refreshRate).change( function() {
                $.plush.refreshRate = $("#refreshRate-option").val();
                $.cookie('Plush2Refresh', $.plush.refreshRate, { expires: 365 });
                
                if ($.plush.refreshRate > 0)
                    $.plush.refresh();
                else
                    clearTimeout($.plush.timeout);
            });
            
            // Max Speed main menu input
            $("#maxSpeed-option").focus(function(){ $.plush.focusedOnSpeedChanger = true; })
                                 .blur(function(){ $.plush.focusedOnSpeedChanger = false; });
            $("#maxSpeed-option").change( function() {
                $.ajax({
                    type: "POST",
					url: "tapi",
					data: "mode=config&name=set_speedlimit&value="+$("#maxSpeed-option").val()
				});
            });
            
            // Upon Queue Completion main menu select
            $("#onQueueFinish-option").change( function() {
                $.ajax({
                    type: "POST",
					url: "tapi",
					data: "mode=queue&name=change_complete_action&value="+$("#onQueueFinish-option").val()
				});
            });
                    
            // queue purge
            $('#queue_purge').click(function(event) {
                if(confirm('Sure you want to empty out your Queue?')){
                    $.ajax({
                    	type: "POST",
                        url: "tapi",
						data: "mode=queue&name=delete&value=all",
                        success: function(){
                        	$.plush.refreshQueue()
                        }
                    });
                }
            });
            
            // 6-in-1 queue sort ajax (via main menu)
            $('#sort_by_avg_age_asc, #sort_by_avg_age_desc, #sort_by_name_asc, #sort_by_name_desc, #sort_by_size_asc, #sort_by_size_desc').click(function() {
            
            	switch($(this).attr('id')) {
            		case 'sort_by_avg_age_asc':	sortParams = "avg_age&dir=asc"; break;
            		case 'sort_by_avg_age_desc':sortParams = "avg_age&dir=desc";break;
            		case 'sort_by_name_asc':	sortParams = "name&dir=asc"; 	break;
            		case 'sort_by_name_desc':	sortParams = "name&dir=desc"; 	break;
            		case 'sort_by_size_asc':	sortParams = "size&dir=asc"; 	break;
            		case 'sort_by_size_desc':	sortParams = "size&dir=desc"; 	break;
            		default: return;
            	};
            	
                $.ajax({
                	type: "POST",
                    url: "tapi",
                    data: "mode=queue&name=sort&sort="+sortParams,
                    success: function(){
                        $.plush.refreshQueue()
                    }
                });
            });
        
            // set up "shutdown sabnzbd" from main menu
            $('#shutdown_sabnzbd').click( function(){
                if(confirm('Sure you want to shut down the SABnzbd application?'))
                    window.location='shutdown';
            });
            
            // manual refresh
            $('#manual_refresh_wrapper').click(function(event) {
                $.plush.refreshQueue();
                $.plush.refreshHistory();
            });
            

            /********************************************
            *********************************************
            
                Queue Methods
            
            *********************************************
            ********************************************/
            
            // this code will remain instantiated even when the contents of the queue change
            $('#queueTable').livequery(function() {
            
                // set queue speed limit selector
                if ($("#maxSpeed-option").val() != $.plush.speedlimit && !$.plush.focusedOnSpeedChanger)
                    $("#maxSpeed-option").val($.plush.speedlimit);
                
                // set queue completion script selector
                if ($("#onQueueFinish-option").val() != $.plush.finishaction)
                    $("#onQueueFinish-option").val($.plush.finishaction);
                
                // set queue pause/resume button state
                if ( $.plush.paused && $('#pause_resume').attr('class') != 'tip q_menu_pause q_menu_paused')
                    $('#pause_resume').attr('class','tip q_menu_pause q_menu_paused');
                else if ( !$.plush.paused && $('#pause_resume').attr('class') != 'tip q_menu_pause q_menu_unpaused')
                    $('#pause_resume').attr('class','tip q_menu_pause q_menu_unpaused');
                
                // set queue titlebar stats tooltip (ETA) 
                $('#time-left').attr('title','ETA: '+$.plush.eta);
                
                // set page title + eta/kbpersec stats at top of queue
                if ($.plush.noofslots < 1) {
                    if ($.plush.paused) document.title = 'PAUSED | SABnzbd+ Plush';
                    else                document.title = 'READY | SABnzbd+ Plush';
                    $('#stats_kbpersec').html('&mdash;');
                    $('#stats_eta').html('&mdash;');
                } else if ($.plush.paused) {
                    document.title = 'PAUSED | '+$.plush.mbleft+' MB left | '+$.plush.noofslots+' NZBs';
                    $('#stats_kbpersec').html('&mdash;');
                    $('#stats_eta').html('&mdash;');
                } else {
                    document.title = $.plush.kbpersec+' KB/s | '+$.plush.mbleft+' MB | '+$.plush.timeleft+' left';
                    $('#stats_kbpersec').html($.plush.kbpersec);
                    $('#stats_eta').html($.plush.timeleft);
                }
                
                // update warnings count/latest warning text in main menu
                $('#have_warnings').html('('+$.plush.have_warnings+')');
                if ($.plush.have_warnings > 0)
                    $('#last_warning').html($.plush.last_warning);
                else
                    $('#last_warning').html('nothing to report');
                
                // queue nzb list limit
                $('#queue_view_preference').change(function(){
                    $.plush.queueViewPreference = $('#queue_view_preference').val();
                    $.cookie('queue_view_preference', $.plush.queueViewPreference, { expires: 365 });
                    $.plush.refreshQueue();
                });
                
                // queue drag and drop sorting
                $("#queueTable").tableDnD({
                    onDrop: function(table, row) {
                        if (table.tBodies[0].rows.length < 2)
                            return false;
                        // determine which position the repositioned row is at now
                        for ( var i=0; i < table.tBodies[0].rows.length; i++ ) {
                            if (table.tBodies[0].rows[i].id == row.id) {
				                $.ajax({
				                    type: "POST",
									url: "tapi",
									data: "mode=switch&value="+row.id+"&value2="+i,
									success: function(result){
										// change priority of the nzb if necessary (priority is returned by API)
										var newPriority = $.trim(result.substring(result.length-2));
										if (newPriority != $('#'+row.id+' .options .proc_priority').val())
											$('#'+row.id+' .options .proc_priority').val(newPriority);
									}
								});
                                return false;
                            }
                        }
                    }
                });
                
                // nzb pause/resume toggle ajax
                $('#queueTable .download-title').click(function(event){
                	if ($(event.target).is('a'))
                		return;
                    if ($(this).attr('class') == "download-title download-queued") {
                        $(this).toggleClass('download-queued').toggleClass('download-paused');
		                $.ajax({
		                    type: "POST",
							url: "tapi",
							data: "mode=queue&name=pause&value="+$(this).parent().attr('id')
						});
                    } else if ($(this).attr('class') == "download-title download-active") {
                        $(this).toggleClass('download-active').toggleClass('download-paused');
		                $.ajax({
		                    type: "POST",
							url: "tapi",
							data: "mode=queue&name=pause&value="+$(this).parent().attr('id')
						});
                    } else {
                        $(this).toggleClass('download-queued').toggleClass('download-paused');
		                $.ajax({
		                    type: "POST",
							url: "tapi",
							data: "mode=queue&name=resume&value="+$(this).parent().attr('id')
						});
                    }
                });
                
                // nzb change priority ajax
                $('#queueTable .proc_priority').change(function(){
                	var nzbid = $(this).parent().parent().attr('id');
					var oldPos = $('#'+nzbid)[0].rowIndex;
                    $.ajax({
	                    type: "POST",
						url: "tapi",
                        data: 'mode=queue&name=priority&value='+nzbid+'&value2='+$(this).val(),
                        success: function(newPos){
							// reposition the nzb if necessary (new position is returned by the API)
                        	if (oldPos == newPos)
                        		return;
                        	else if (oldPos < newPos)
	                        	$('#'+nzbid).insertAfter($('#queueTable tr:eq('+ newPos +')'));
							else
	                        	$('#'+nzbid).insertBefore($('#queueTable tr:eq('+ newPos +')'));
                        }
                    });
                });
                
                // 3-in-1 change nzb [category + processing + script] ajax
                $('.change_cat, .change_opts, .change_script').change(function(){
	                $.ajax({
	                    type: "POST",
						url: "tapi",
						data: "mode="+$(this).attr('class')+"&value="+$(this).parent().parent().attr('id')+'&value2='+$(this).val()
					});
                });
                
                // for skipping queue refresh on mouseover
                $('#queueTable').bind("mouseover", function(){ $.plush.skipRefresh=true; });
                $('#queueTable').bind("mouseout", function(){ $.plush.skipRefresh=false; });
                $('.box_fatbottom').bind("mouseover mouseout", function(){ $.plush.skipRefresh=false; });
                
                // tooltips for options & time left / ETA
                $('#time-left, select').tooltip({
                    extraClass:    "tooltip",
                    track:        true, 
                    fixPNG:        true
                });
                
            }); // end livequery
            
            // queue pause/resume
            $('#pause_resume').click(function(event) {
                if ($(event.target).attr('class') == 'tip q_menu_pause q_menu_paused')
	                $.ajax({
	                    type: "POST",
						url: "tapi",
						data: "mode=resume"
					});
                else
	                $.ajax({
	                    type: "POST",
						url: "tapi",
						data: "mode=pause"
					});
                if ($('#pause_resume').attr('class') == 'tip q_menu_pause q_menu_paused')
                    $('#pause_resume').attr('class','tip q_menu_pause q_menu_unpaused');
                else
                    $('#pause_resume').attr('class','tip q_menu_pause q_menu_paused');
            });
            
            // queue singular nzb deletion
            $('#queue').click(function(event) {
                if ($(event.target).is('.queue_delete') && confirm('Delete NZB? Are you sure?') ) {
                    delid = $(event.target).parent().parent().attr('id');
                    $('#'+delid).fadeOut('fast');
	                $.ajax({
	                    type: "POST",
						url: "tapi",
						data: "mode=queue&name=delete&value="+delid
					});
                }
            });
            
            
            /********************************************
            *********************************************
            
                History Methods
            
            *********************************************
            ********************************************/
            
            // history purge
            $('.h_menu_purge').click(function(event) {
	            if (confirm("Are you sure you want to purge the history?")) {
                    $.ajax({
	                    type: "POST",
						url: "tapi",
                        data: 'mode=history&name=delete&value=all',
                        success: function(){
                            $.plush.refreshHistory()
                        }
                    });
                }
            });
            
            // history singular nzb deletion
            $('#history').click(function(event) {
                if ($(event.target).is('.queue_delete')) {    // history delete
                    delid = $(event.target).parent().parent().attr('id');
                    $('#'+delid).fadeOut('fast');
	                $.ajax({
	                    type: "POST",
						url: "tapi",
						data: "mode=history&name=delete&value="+delid
					});
                }
            });
            
            // this code will remain instantiated even when the contents of the history change
            $('#history .left_stats').livequery(function() {

                // history view limiter
                $('#history_view_preference').change(function(){
                    $.plush.historyViewPreference = $('#history_view_preference').val();
                    $.cookie('history_view_preference', $.plush.historyViewPreference, { expires: 365 });
                    $.plush.refreshHistory();
                });

            }); // end livequery
            
            // this code will remain instantiated even when the contents of the history change
            $('#historyTable').livequery(function() {
                
                // tooltips for verbose notices
                $('#history .verbose div, #history .tip').tooltip({
                    extraClass:    "tooltip",
                    track:        true, 
                    fixPNG:        true
                });
                
            }); // end livequery
            
            
            /********************************************
            *********************************************
        
                Miscellaneous Methods
                
            *********************************************
            ********************************************/
            
            // restore queue/history view preferences (or set to defaults)
            if ($.cookie('queue_view_preference'))
                $.plush.queueViewPreference = $.cookie('queue_view_preference');
            if ($.cookie('history_view_preference'))
                $.plush.historyViewPreference = $.cookie('history_view_preference');
            
            // additional tooltips
            $('.tip').tooltip({
                extraClass:    "tooltip",
                track:        true, 
                fixPNG:        true
            });
            
            // fix IE6 .png image transparencies
            $('img[@src$=.png], div.history_logo, div.queue_logo, li.q_menu_addnzb, li.q_menu_pause, li.h_menu_verbose, li.h_menu_purge, div#time-left, div#speed').ifixpng();
            
        } // end initEvents()
        
    }; // end plush object

});


// once the DOM is ready, run this
jQuery(document).ready(function($){

    // initialize plush
    $.plush.initEvents();

    // initiate refresh cycle
    $.plush.refresh();
    
});

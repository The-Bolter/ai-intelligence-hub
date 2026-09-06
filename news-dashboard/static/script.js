(function(){
"use strict";

var currentCat="ai",aiData=null,weeklyData=null,todayNewData=null,isLoading=false;
var STATIC_MODE=typeof window!=="undefined"&&(window.STATIC_MODE===true||window.STATIC_MODE==="true");
var importanceFilter="all",categoryFilter="all",contentTypeFilter="all",eventTypeFilter="all",searchQuery="";
var aiExpanded={updates:false,trends:false,resources:false};
var AI_OVERVIEW_LIMIT={updates:5,trends:4,resources:4};
var AI_CONTENT_CN={"updates":"动态","resources":"AI资源","trend":"趋势"};
var AI_CATEGORY_CN={"company":"企业动态","model_update":"模型更新","product_update":"产品/工具更新","breakthrough":"技术突破","agent":"Agent","model":"模型","tool":"工具","app":"应用","tech_direction":"技术方向","market_change":"市场变化","community_hotspot":"社区热点"};
var AI_SECONDARY={"updates":["company","model_update","product_update","breakthrough"],"resources":["agent","model","tool","app"],"trend":["tech_direction","market_change","community_hotspot"]};
var GAMING_EVENTS=[
  ["all","全部"],["major_update","大版本"],["monthly_update","月度更新"],
  ["weekly_update","周更新"],["season_start","赛季"],["new_map","新地图"],
  ["new_character","新角色"],["collaboration","联动"],["major_event","大型活动"],
  ["test_or_launch","测试/上线"],["esports","赛事"]
];
var tabs=document.querySelectorAll(".tab");
var filterBar=document.getElementById("filterBar");
var aiFilterBar=document.getElementById("aiFilterBar");
var aiDashboard=document.getElementById("aiDashboard");
var gamingDashboard=document.getElementById("gamingDashboard");
var btnRefresh=document.getElementById("btnRefresh");
var statusDot=document.getElementById("statusDot");
var statusText=document.getElementById("statusText");
var dateDisplay=document.getElementById("dateDisplay");
var searchInput=document.getElementById("searchInput");
var searchClear=document.getElementById("searchClear");
var searchTimer=null;
var weeklyBoard=document.getElementById("weeklyBoard");
var eventDrawer=document.getElementById("eventDrawer");
var eventDrawerBody=document.getElementById("eventDrawerBody");
var eventDrawerClose=document.getElementById("eventDrawerClose");
var eventDrawerBackdrop=document.getElementById("eventDrawerBackdrop");
var activeEventId="";

function esc(value){
  if(value===null||value===undefined)return"";
  var d=document.createElement("div");
  d.appendChild(document.createTextNode(String(value)));
  return d.innerHTML;
}
function safeUrl(value){
  var url=String(value||"").trim();
  return /^https?:\/\//i.test(url)?esc(url):"#";
}
function array(value){return Array.isArray(value)?value:[];}
function setStatus(state,label){
  statusDot.className="status-dot "+state;
  statusText.textContent=label||({ready:"就绪",loading:"加载中...",error:"加载失败"}[state]||state);
}
function staticDataPath(apiPath){
  if(!STATIC_MODE)return apiPath;
  var paths={
    "/api/ai/today":"data/ai_today.json",
    "/api/gaming/weekly":"data/gaming_weekly.json",
    "/api/gaming/today-new":"data/gaming_today_new.json"
  };
  if(paths[apiPath])return paths[apiPath];
  if(apiPath.indexOf("/api/gaming/events/")===0){
    return "data/gaming_events/"+apiPath.slice("/api/gaming/events/".length)+".json";
  }
  return apiPath;
}
function fetchJson(path){
  path=staticDataPath(path);
  return fetch(path+(path.indexOf("?")===-1?"?":"&")+"_="+Date.now(),{headers:{Accept:"application/json"}})
    .then(function(response){if(!response.ok)throw new Error("HTTP "+response.status);return response.json();});
}
function timeAgo(iso){
  if(!iso)return"";
  var time=new Date(iso).getTime();
  if(!isFinite(time))return String(iso);
  var seconds=Math.max(0,(Date.now()-time)/1000);
  if(seconds<60)return"刚刚";
  if(seconds<3600)return Math.floor(seconds/60)+"分钟前";
  if(seconds<86400)return Math.floor(seconds/3600)+"小时前";
  return Math.floor(seconds/86400)+"天前";
}
function dateLabel(value,withTime){
  if(!value)return"待确认";
  var raw=String(value);
  var date=/^\d{4}-\d{2}-\d{2}$/.test(raw)?new Date(raw+"T12:00:00+08:00"):new Date(raw);
  if(!isFinite(date.getTime()))return raw;
  var options=withTime?{month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit",hour12:false}:{month:"numeric",day:"numeric"};
  return new Intl.DateTimeFormat("zh-CN",options).format(date).replace(/\//g,".");
}
function businessDateLabel(value){
  var match=/^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value||""));
  if(match){
    var year=Number(match[1]),month=Number(match[2]),day=Number(match[3]);
    var weekday=["日","一","二","三","四","五","六"][new Date(Date.UTC(year,month-1,day)).getUTCDay()];
    return year+"年"+String(month).padStart(2,"0")+"月"+String(day).padStart(2,"0")+"日 星期"+weekday;
  }
  var parts=new Intl.DateTimeFormat("en-CA",{timeZone:"Asia/Shanghai",year:"numeric",month:"2-digit",day:"2-digit"}).formatToParts(new Date());
  var values={};
  parts.forEach(function(part){values[part.type]=part.value;});
  return businessDateLabel(values.year+"-"+values.month+"-"+values.day);
}
function summaryOf(item){return item.summary_cn||item.chinese_summary||item.summary||"暂无摘要";}
function titleOf(item){return item.title_cn||item.title||item.headline||"未命名";}
function sourceOf(item){return item.source_name||item.source||"未知来源";}
function linkOf(item){return item.url||item.link||"";}
function isGithub(item){return String(item.source_type||"").toLowerCase()==="github"||String(item.source||"").toLowerCase()==="github"||item.is_github===true;}
function emptyState(message,detail){
  return '<div class="module-empty"><strong>'+esc(message)+'</strong>'+(detail?'<p>'+esc(detail)+'</p>':'')+'</div>';
}
function errorState(message,endpoint){
  return '<div class="module-empty module-error"><strong>'+esc(message)+'</strong><p>'+esc(endpoint)+' 暂时不可用，请稍后重试。</p></div>';
}

function matchQuery(item){
  var q=searchQuery.trim().toLowerCase();
  if(!q)return true;
  var fields=[titleOf(item),summaryOf(item),sourceOf(item),item.category,item.content_type];
  return fields.some(function(value){return String(value||"").toLowerCase().indexOf(q)!==-1;});
}
function filterAiItems(items,sectionType){
  return array(items).filter(function(item){
    if(contentTypeFilter!=="all"&&contentTypeFilter!==sectionType)return false;
    if(categoryFilter!=="all"&&item.category!==categoryFilter)return false;
    if(importanceFilter!=="all"&&item.importance!==importanceFilter)return false;
    return matchQuery(item);
  });
}
function filterWeeklyEvents(items){
  return array(items).filter(function(item){return eventTypeFilter==="all"||item.event_type===eventTypeFilter;});
}

function button(kind,value,label,active){
  return '<button class="fb-btn fb-'+kind+' '+(active?'active':'')+'" type="button" data-f="'+kind+'" data-v="'+esc(value)+'">'+esc(label)+'</button>';
}
function buildFilters(){
  var html="";
  if(currentCat==="ai"){
    html+='<div class="filter-row"><span class="filter-lbl">重要性:</span>';
    ["all","S","A","B","C","D"].forEach(function(value){html+=button("imp",value,value==="all"?"全部":value,importanceFilter===value);});
    html+='</div><div class="filter-row"><span class="filter-lbl">一级:</span>';
    [["all","全部"],["updates","动态"],["resources","AI资源"],["trend","趋势"]].forEach(function(item){html+=button("type",item[0],item[1],contentTypeFilter===item[0]);});
    html+='</div>';
    if(contentTypeFilter!=="all"){
      html+='<div class="filter-row"><span class="filter-lbl">二级:</span>'+button("cat","all","全部",categoryFilter==="all");
      array(AI_SECONDARY[contentTypeFilter]).forEach(function(value){html+=button("cat",value,AI_CATEGORY_CN[value]||value,categoryFilter===value);});
      html+='</div>';
    }
    html+='<div class="filter-hint">筛选仅作用于最新动态、趋势信号和 AI资源；今日重点保持完整。</div>';
  }else{
    html+='<div class="filter-row"><span class="filter-lbl">事件:</span>';
    GAMING_EVENTS.forEach(function(item){html+=button("event",item[0],item[1],eventTypeFilter===item[0]);});
    html+='</div>';
  }
  (currentCat==="ai"?aiFilterBar:filterBar).innerHTML=html;
}

function importanceBadge(importance){
  if(!importance)return"";
  return '<span class="importance-pill importance-'+esc(String(importance).toLowerCase())+'">'+esc(importance)+' 级</span>';
}
function renderPriorityCard(item){
  return '<article class="priority-card">'+
    '<div class="priority-meta">'+importanceBadge(item.importance)+'<span>'+esc(sourceOf(item))+'</span><span>'+esc(item.published_ago||timeAgo(item.published_at||item.published))+'</span></div>'+
    '<h4><a href="'+safeUrl(linkOf(item))+'" target="_blank" rel="noopener noreferrer">'+esc(titleOf(item))+'</a></h4>'+
    '<p>'+esc(summaryOf(item))+'</p>'+
  '</article>';
}
function renderAiCard(item){
  var category=AI_CATEGORY_CN[item.category]||item.category||"AI 情报";
  return '<article class="intel-row">'+
    '<div class="intel-main"><div class="intel-meta"><span class="cat-tag">'+esc(category)+'</span><span>'+esc(sourceOf(item))+'</span><span>'+esc(item.published_ago||timeAgo(item.published_at||item.published))+'</span></div>'+
    '<h4><a href="'+safeUrl(linkOf(item))+'" target="_blank" rel="noopener noreferrer">'+esc(titleOf(item))+'</a></h4><p>'+esc(summaryOf(item))+'</p></div>'+importanceBadge(item.importance)+
  '</article>';
}
function githubStat(label,value){return '<span class="gh-stat"><span class="gh-stat-label">'+esc(label)+'</span><strong>'+esc(value===undefined||value===null?"--":value)+'</strong></span>';}
function renderGithubCard(item){
  var metadata=item.metadata||{};
  return '<article class="github-radar-card">'+
    '<div class="github-radar-meta"><span class="github-badge">GitHub</span>'+importanceBadge(item.importance)+'</div>'+
    '<h4><a href="'+safeUrl(linkOf(item))+'" target="_blank" rel="noopener noreferrer">'+esc(titleOf(item))+'</a></h4>'+
    '<p>'+esc(summaryOf(item))+'</p><div class="github-stats">'+
    githubStat("Stars",item.stars!=null?item.stars:metadata.stars)+githubStat("Forks",item.forks!=null?item.forks:metadata.forks)+githubStat("Score",item.github_score)+
    '</div></article>';
}
function resetAiExpanded(){aiExpanded={updates:false,trends:false,resources:false};}
function renderAiList(sectionType,targetId,countId,toggleId,items,emptyMessage){
  var target=document.getElementById(targetId),count=document.getElementById(countId);
  var toggle=document.getElementById(toggleId),limit=AI_OVERVIEW_LIMIT[sectionType],expanded=aiExpanded[sectionType];
  var visible=expanded?items:items.slice(0,limit);
  count.textContent=items.length+" 条";
  toggle.hidden=items.length<=limit;
  toggle.textContent=expanded?"收起":"查看更多（共 "+items.length+" 条）";
  toggle.setAttribute("aria-expanded",expanded?"true":"false");
  target.innerHTML=visible.length?visible.map(renderAiCard).join(""):emptyState(emptyMessage,"可调整筛选或搜索条件。");
}
function renderAi(){
  if(!aiData)return;
  var priority=array(aiData.today_priority).filter(function(item){return !isGithub(item);}).slice(0,5);
  document.getElementById("aiPriority").innerHTML=priority.length?priority.map(renderPriorityCard).join(""):emptyState("今日暂无重点情报");
  renderAiList("updates","aiUpdates","updatesCount","updatesToggle",filterAiItems(aiData.updates,"updates"),"暂无匹配的最新动态");
  renderAiList("trends","aiTrends","trendsCount","trendsToggle",filterAiItems(aiData.trends,"trend"),"暂无匹配的趋势信号");
  renderAiList("resources","aiResources","resourcesCount","resourcesToggle",filterAiItems(aiData.resources,"resources"),"暂无匹配的 AI资源");
  var radar=array(aiData.github_radar).slice(0,5);
  document.getElementById("githubRadar").innerHTML=radar.length?radar.map(renderGithubCard).join(""):emptyState("今日暂无 GitHub 项目");
  document.getElementById("aiDate").textContent=aiData.date||"";
  dateDisplay.textContent=businessDateLabel(aiData.date);
  document.getElementById("aiUpdated").textContent=aiData.generated_at?"数据更新于 "+timeAgo(aiData.generated_at):"";
}

function weeklyEvents(data){
  if(Array.isArray(data))return data;
  return array(data&&data.events).length?data.events:array(data&&data.items).length?data.items:array(data&&data.weekly_events).length?data.weekly_events:array(data&&data.weekly);
}
function todayItems(data){
  if(Array.isArray(data))return data;
  return array(data&&data.items).length?data.items:array(data&&data.events).length?data.events:array(data&&data.new_items).length?data.new_items:array(data&&data.today_new);
}
function groupKey(item){
  var value=String(item.display_group||"").toLowerCase();
  if(value==="mobile"||value.indexOf("手游")!==-1)return"mobile";
  if(value==="pc"||value.indexOf("端游")!==-1||value.indexOf("console")!==-1)return"pc";
  return"other";
}
function groupLabel(key){return key==="mobile"?"手游":key==="pc"?"端游":"其他";}
function eventTypeLabel(value){
  for(var i=0;i<GAMING_EVENTS.length;i++)if(GAMING_EVENTS[i][0]===value)return GAMING_EVENTS[i][1];
  return value||"事件";
}
function eventDateRange(item){
  if(item.date_range)return String(item.date_range);
  var start=item.start_date||item.event_date||item.date;
  var end=item.end_date;
  if(!start)return"日期待确认";
  if(end&&end!==start)return dateLabel(start,false)+" — "+dateLabel(end,false);
  return dateLabel(start,false);
}
function changesText(value){
  if(Array.isArray(value))return value.filter(Boolean).join(" · ");
  if(value&&typeof value==="object")return Object.keys(value).filter(function(key){return value[key];}).map(function(key){return value[key];}).join(" · ");
  return value||"详情待更新";
}
function attentionClass(value){
  var text=String(value||"").toLowerCase();
  if(text==="high"||text.indexOf("高")!==-1)return"high";
  if(text==="medium"||text.indexOf("中")!==-1)return"medium";
  return"normal";
}
function attentionText(value){
  var text=String(value||"");
  if(!text)return"常规";
  if(text.toLowerCase()==="high")return"高";
  if(text.toLowerCase()==="medium")return"中";
  if(text.toLowerCase()==="low")return"低";
  return text;
}
function sourceList(value){
  if(Array.isArray(value))return value;
  return value?[value]:[];
}
function sourceUrl(source){
  if(typeof source==="string")return /^https?:\/\//i.test(source)?source:"";
  return source&&source.url?String(source.url):"";
}
function sourceText(source){
  if(typeof source==="string")return"";
  return [source&&source.source_type,source&&source.name,source&&source.label,source&&source.fetch_method].filter(Boolean).join(" ").toLowerCase();
}
function isOfficialSource(source){
  return !!(source&&typeof source==="object"&&source.official===true)||/official|verification|官方|官网/.test(sourceText(source));
}
function firstSource(sources,officialOnly){
  var list=sourceList(sources);
  for(var i=0;i<list.length;i++){
    if(sourceUrl(list[i])&&(!officialOnly||isOfficialSource(list[i])))return list[i];
  }
  return null;
}
function recommendedArticleSource(item){
  var articles=sourceList(item.source_articles),recommended=sourceList(item.recommended_sources);
  for(var i=0;i<recommended.length;i++){
    var recommendedUrl=sourceUrl(recommended[i]);
    if(!recommendedUrl||!isOfficialSource(recommended[i]))continue;
    for(var j=0;j<articles.length;j++)if(recommendedUrl===sourceUrl(articles[j]))return recommended[i];
  }
  return null;
}
function weeklySource(item){
  var source=recommendedArticleSource(item)||firstSource(item.recommended_sources,true);
  if(!source)source=firstSource(item.source_articles,true)||firstSource(item.source_articles,false);
  if(!source)source=firstSource(item.discovery_sources,true)||firstSource(item.discovery_sources,false);
  if(!source)return null;
  var verification=String(item.verification_level||"").toLowerCase();
  var crosscheck=verification==="secondary_crosscheck"||/secondary|crosscheck|交叉/.test(sourceText(source));
  return {url:sourceUrl(source),label:crosscheck?"交叉验证 ↗":isOfficialSource(source)?"官方公告 ↗":"官方来源 ↗"};
}
function isPendingVerification(item){
  return ["questionable","unverified","pending"].indexOf(String(item.verification_level||"").toLowerCase())!==-1;
}
function renderWeeklyCard(item){
  var source=weeklySource(item),eventId=String(item.event_id||"").trim();
  var interactive=eventId?' is-event-clickable':'';
  var attributes=eventId?' data-event-id="'+esc(eventId)+'" role="button" tabindex="0" aria-label="查看 '+esc(item.game_name||item.game||"游戏")+' 事件详情"':'';
  return '<article class="weekly-event-card'+interactive+'"'+attributes+'>'+
    '<div class="event-date-block"><strong>'+esc(eventDateRange(item))+'</strong><span>'+esc(eventTypeLabel(item.event_type))+'</span></div>'+
    '<div class="event-copy"><span class="game-name">'+esc(item.game_name||item.game||"未知游戏")+'</span><h4>'+esc(item.event_name||item.headline||"未命名事件")+'</h4><p>'+esc(changesText(item.key_changes||item.summary))+'</p><div class="event-foot">'+
    '<span class="attention attention-'+attentionClass(item.attention_level)+'">关注度：'+esc(attentionText(item.attention_level))+'</span>'+
    (item.phase?'<span class="phase-pill">'+esc(item.phase)+'</span>':'')+
    (item.hotspot_score!=null?'<span class="weak-score">热度 '+esc(item.hotspot_score)+'</span>':'')+
    (source?'<a class="event-source-link" href="'+safeUrl(source.url)+'" target="_blank" rel="noopener noreferrer">'+esc(source.label)+'</a>':'')+
    (isPendingVerification(item)?'<span class="verification-pending">待核验</span>':'')+
    '</div></div></article>';
}
function eventStatusLabel(value){
  return {upcoming:"即将开始",active:"进行中",ended:"已结束",unknown:"时间待确认"}[String(value||"").toLowerCase()]||"时间待确认";
}
function eventDetailDateRange(item){
  if(!item.start_date)return"时间待确认";
  if(item.end_date&&item.end_date!==item.start_date)return dateLabel(item.start_date,false)+" — "+dateLabel(item.end_date,false);
  return dateLabel(item.start_date,false);
}
function drawerExternalLink(url,label,className){
  if(!url)return esc(label);
  return '<a class="'+(className||"drawer-link")+'" href="'+safeUrl(url)+'" target="_blank" rel="noopener noreferrer">'+esc(label)+'</a>';
}
function renderEventDrawer(data){
  var timeline=array(data.timeline),sources=array(data.sources);
  var verification=String(data.verification_status||"partial").toLowerCase()==="verified"?"VERIFIED":"PARTIAL";
  var why=String(data.why_it_matters||"").trim();
  var timelineHtml=timeline.length?timeline.map(function(item){
    var source=item.source_name?drawerExternalLink(item.source_url,item.source_name,"timeline-source"):"";
    return '<li class="event-timeline-item"><time>'+esc(dateLabel(item.date,true))+'</time><div><p>'+esc(item.text||"")+'</p>'+(source?'<span>'+source+'</span>':'')+'</div></li>';
  }).join(""):'<div class="drawer-empty">暂无足够可验证的事件时间线</div>';
  var sourcesHtml=sources.length?sources.map(function(item){
    var meta=[item.source_type,item.published_at?dateLabel(item.published_at,true):""].filter(Boolean).map(esc).join(" · ");
    return '<li class="evidence-item"><div><strong>'+esc(item.source_name||"未命名来源")+'</strong>'+(meta?'<span>'+meta+'</span>':'')+'</div>'+drawerExternalLink(item.url,"原文 ↗","evidence-link")+'</li>';
  }).join(""):'<div class="drawer-empty">暂无可展示的验证来源</div>';
  eventDrawerBody.innerHTML='<div class="event-detail-title"><span class="game-name">'+esc(data.game_name||"未知游戏")+'</span><h2>'+esc(data.title||"未命名事件")+'</h2><span class="verification-badge verification-'+verification.toLowerCase()+'">'+verification+'</span></div>'+
    '<dl class="event-detail-meta"><div><dt>事件日期</dt><dd>'+esc(eventDetailDateRange(data))+'</dd></div><div><dt>状态</dt><dd>'+esc(eventStatusLabel(data.status))+'</dd></div><div><dt>关注度</dt><dd>'+esc(data.attention_score==null?"--":data.attention_score)+'</dd></div></dl>'+
    (why?'<section class="drawer-section"><h3>为什么值得关注</h3><p class="why-it-matters">'+esc(why)+'</p></section>':'')+
    '<section class="drawer-section"><h3>事件时间线</h3><ol class="event-timeline">'+timelineHtml+'</ol></section>'+
    '<section class="drawer-section"><h3>验证来源</h3><ul class="evidence-list">'+sourcesHtml+'</ul></section>';
}
function renderEventDrawerState(message,detail){
  eventDrawerBody.innerHTML='<div class="drawer-state"><strong>'+esc(message)+'</strong>'+(detail?'<p>'+esc(detail)+'</p>':'')+'</div>';
}
function closeEventDrawer(){
  activeEventId="";
  eventDrawer.classList.remove("is-open");eventDrawer.setAttribute("aria-hidden","true");
  eventDrawerBackdrop.hidden=true;
}
function openEventDrawer(eventId){
  if(!eventId)return;
  activeEventId=eventId;
  eventDrawer.classList.add("is-open");eventDrawer.setAttribute("aria-hidden","false");
  eventDrawerBackdrop.hidden=false;
  renderEventDrawerState("正在加载事件详情...");
  fetchJson("/api/gaming/events/"+encodeURIComponent(eventId)).then(function(data){
    if(activeEventId===eventId)renderEventDrawer(data||{});
  }).catch(function(error){
    if(activeEventId!==eventId)return;
    if(error&&error.message==="HTTP 404")renderEventDrawerState("该事件详情暂不可用","事件可能尚未写入可查询的详情库。");
    else renderEventDrawerState("事件详情加载失败","请稍后重试。");
  });
}
function renderWeekly(){
  if(!weeklyData)return;
  var events=filterWeeklyEvents(weeklyEvents(weeklyData));
  var groups={mobile:[],pc:[],other:[]};
  events.forEach(function(item){groups[groupKey(item)].push(item);});
  var html="";
  ["mobile","pc","other"].forEach(function(key){
    if(key==="other"&&!groups[key].length)return;
    html+='<section class="game-group"><div class="game-group-header"><h3>【'+groupLabel(key)+'】</h3><span>'+groups[key].length+' 条</span></div>';
    html+=groups[key].length?'<div class="weekly-event-list">'+groups[key].map(renderWeeklyCard).join("")+'</div>':emptyState("本周暂无已确认事件");
    html+='</section>';
  });
  document.getElementById("weeklyBoard").innerHTML=html||emptyState("本周暂无已确认事件");
  var start=weeklyData.week_start||weeklyData.start_date,end=weeklyData.week_end||weeklyData.end_date;
  document.getElementById("gamingWeekRange").textContent=start?(dateLabel(start,false)+(end?" — "+dateLabel(end,false):"")):"本周";
  document.getElementById("gamingUpdated").textContent=weeklyData.generated_at?"数据更新于 "+timeAgo(weeklyData.generated_at):"";
}
function findWeeklyMatch(item){
  var game=String(item.game_name||item.game||"").toLowerCase(),name=String(item.event_name||item.headline||"").toLowerCase();
  return weeklyEvents(weeklyData).find(function(event){return String(event.game_name||event.game||"").toLowerCase()===game&&String(event.event_name||event.headline||"").toLowerCase()===name;});
}
function renderTodayNew(){
  if(!todayNewData)return;
  var items=todayItems(todayNewData);
  document.getElementById("todayNewList").innerHTML=items.length?items.map(function(item){
    var match=findWeeklyMatch(item)||{},attention=item.attention_level||match.attention_level;
    return '<article class="today-new-card"><div class="today-new-time">'+esc(dateLabel(item.detected_at,true))+'</div><h4>'+esc(item.game_name||item.game||"未知游戏")+'</h4><p>'+esc(item.event_name||item.headline||"新事件")+'</p><div class="today-new-meta"><span>开始 '+esc(dateLabel(item.start_date||item.event_date,false))+'</span>'+
      (attention?'<span class="attention attention-'+attentionClass(attention)+'">关注度：'+esc(attentionText(attention))+'</span>':'')+'</div></article>';
  }).join(""):'<div class="today-new-empty">今日暂无新增</div>';
}

function loadAi(){
  isLoading=true;setStatus("loading","加载 AI 情报...");btnRefresh.classList.add("spinning");
  document.getElementById("aiPriority").innerHTML='<div class="loading-spinner">加载中...</div>';
  return fetchJson("/api/ai/today").then(function(data){
    aiData=data||{};renderAi();setStatus("ready");
  }).catch(function(){
    aiData=null;
    document.getElementById("aiPriority").innerHTML=errorState("今日 AI 情报加载失败","/api/ai/today");
    ["aiUpdates","aiTrends","aiResources","githubRadar"].forEach(function(id){document.getElementById(id).innerHTML=emptyState("暂无数据");});
    setStatus("error","AI 接口不可用");
  }).then(function(){isLoading=false;btnRefresh.classList.remove("spinning");});
}
function loadGaming(){
  isLoading=true;setStatus("loading","加载 Gaming 周报...");btnRefresh.classList.add("spinning");
  document.getElementById("weeklyBoard").innerHTML='<div class="loading-spinner">加载本周热点...</div>';
  document.getElementById("todayNewList").innerHTML='<div class="loading-spinner">加载中...</div>';
  var weeklyRequest=fetchJson("/api/gaming/weekly").then(function(data){weeklyData=data||{};renderWeekly();}).catch(function(error){
    weeklyData=null;document.getElementById("weeklyBoard").innerHTML=errorState("本周热点加载失败","/api/gaming/weekly");throw error;
  });
  var todayRequest=fetchJson("/api/gaming/today-new").then(function(data){todayNewData=data||{};renderTodayNew();}).catch(function(error){
    todayNewData=null;document.getElementById("todayNewList").innerHTML=errorState("今日新增加载失败","/api/gaming/today-new");throw error;
  });
  return Promise.allSettled([weeklyRequest,todayRequest]).then(function(results){
    var failed=results.some(function(result){return result.status==="rejected";});
    setStatus(failed?"error":"ready",failed?"部分接口不可用":"就绪");isLoading=false;btnRefresh.classList.remove("spinning");
  });
}
function renderCurrent(){if(currentCat==="ai")renderAi();else renderWeekly();}
function applyTabVisibility(category){
  var isAi=category==="ai";
  aiDashboard.hidden=!isAi;
  gamingDashboard.hidden=isAi;
  aiFilterBar.hidden=!isAi;
  filterBar.hidden=isAi;
  filterBar.classList.toggle("gaming-filters",!isAi);
}
function switchTab(category){
  currentCat=category;importanceFilter="all";categoryFilter="all";contentTypeFilter="all";eventTypeFilter="all";searchQuery="";
  if(searchTimer)clearTimeout(searchTimer);
  searchInput.value="";searchClear.classList.remove("visible");
  tabs.forEach(function(tab){tab.classList.toggle("active",tab.dataset.category===category);});
  applyTabVisibility(category);
  buildFilters();
  if(category==="ai"){if(aiData)renderAi();else loadAi();}
  else if(weeklyData||todayNewData){renderWeekly();renderTodayNew();}else loadGaming();
}

function handleFilterClick(event){
  var target=event.target.closest(".fb-btn");if(!target)return;
  var type=target.dataset.f,value=target.dataset.v;
  if(type==="imp")importanceFilter=value;
  if(type==="cat")categoryFilter=value;
  if(type==="type"&&value!==contentTypeFilter){contentTypeFilter=value;categoryFilter="all";}
  if(type==="event")eventTypeFilter=value;
  if(currentCat==="ai")resetAiExpanded();
  buildFilters();renderCurrent();
}
filterBar.addEventListener("click",handleFilterClick);
aiFilterBar.addEventListener("click",handleFilterClick);
weeklyBoard.addEventListener("click",function(event){
  if(event.target.closest("a,button"))return;
  var card=event.target.closest(".weekly-event-card[data-event-id]");
  if(card&&weeklyBoard.contains(card))openEventDrawer(card.dataset.eventId);
});
weeklyBoard.addEventListener("keydown",function(event){
  if(event.key!=="Enter"&&event.key!==" ")return;
  var card=event.target.closest(".weekly-event-card[data-event-id]");
  if(card&&weeklyBoard.contains(card)){event.preventDefault();openEventDrawer(card.dataset.eventId);}
});
function closeEventDrawerFromControl(event){
  event.preventDefault();
  event.stopPropagation();
  closeEventDrawer();
}
eventDrawerClose.addEventListener("pointerdown",closeEventDrawerFromControl);
eventDrawerClose.addEventListener("click",closeEventDrawerFromControl);
eventDrawerBackdrop.addEventListener("click",closeEventDrawer);
document.addEventListener("keydown",function(event){if(event.key==="Escape"&&eventDrawer.classList.contains("is-open"))closeEventDrawer();});
aiDashboard.addEventListener("click",function(event){
  var target=event.target.closest("[data-ai-expand]");if(!target)return;
  var section=target.dataset.aiExpand;
  aiExpanded[section]=!aiExpanded[section];renderAi();
});
tabs.forEach(function(tab){tab.addEventListener("click",function(){switchTab(tab.dataset.category);});});
btnRefresh.addEventListener("click",function(){if(isLoading)return;if(currentCat==="ai")loadAi();else loadGaming();});
searchInput.addEventListener("input",function(){
  clearTimeout(searchTimer);searchTimer=setTimeout(function(){searchQuery=searchInput.value;resetAiExpanded();searchClear.classList.toggle("visible",searchQuery.length>0);renderAi();},150);
});
searchClear.addEventListener("click",function(){searchInput.value="";searchQuery="";resetAiExpanded();searchClear.classList.remove("visible");renderAi();searchInput.focus();});
dateDisplay.textContent=businessDateLabel();
applyTabVisibility(currentCat);
buildFilters();loadAi();
setInterval(function(){if(currentCat==="ai")loadAi();else loadGaming();},300000);
})();

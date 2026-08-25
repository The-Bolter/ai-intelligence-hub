import pathlib, os, py_compile

def W(*cs):
    return ''.join(chr(c) for c in cs)

d = pathlib.Path(r'C:\Users\L1352\Documents\New project\news-dashboard')
L = []

def Q(s):
    return '"' + s + '"'

def kw_pair(k, v):
    return '    ' + Q(k) + ': ' + v + ','

def kw_list(items):
    return '[' + ', '.join(Q(x) for x in items) + ']'

# AI_TECH_TYPE_KEYWORDS
L.append('AI_TECH_TYPE_KEYWORDS = {')
L.append(kw_pair('LLM', kw_list(['large language model','llm','language model','transformer','foundation model','pretrained','pre-trained','ai','model','neural','chatbot','training','inference'])))
L.append(kw_pair('Agent', kw_list(['agent',W(0x667A,0x80FD,0x4F53),'tool use','function calling','rag','multi-agent','orchestration',W(0x63A8,0x7406),'reasoning'])))
L.append(kw_pair('Image Generation', kw_list(['image generation','text-to-image','stable diffusion','dall-e','midjourney',W(0x56FE,0x50CF,0x751F,0x6210),W(0x6587,0x751F,0x56FE)])))
L.append(kw_pair('Video Generation', kw_list(['video generation','text-to-video','sora',W(0x89C6,0x9891,0x751F,0x6210),W(0x6587,0x751F,0x89C6,0x9891)])))
L.append(kw_pair('Audio/Speech', kw_list(['speech','tts','voice','music generation',W(0x8BED,0x97F3),W(0x97F3,0x4E50,0x751F,0x6210)])))
L.append(kw_pair('Multimodal', kw_list(['multimodal','vision-language',W(0x591A,0x6A21,0x6001),'visual question answering','vqa'])))
L.append(kw_pair('Code Generation', kw_list(['code generation','code completion','code review',W(0x4EE3,0x7801,0x751F,0x6210),W(0x7F16,0x7A0B)])))
L.append('    "Other": [],')
L.append('}')
L.append('')

# AI_APPLICATION_KEYWORDS
L.append('AI_APPLICATION_KEYWORDS = {')
L.append(kw_pair('Development', kw_list(['code','programming','ide','cursor','copilot','api','sdk','framework',W(0x5F00,0x53D1),W(0x7F16,0x7A0B)])))
L.append(kw_pair('Creation', kw_list(['create','design','image','video','music',W(0x521B,0x4F5C),W(0x8BBE,0x8BA1),W(0x751F,0x6210)])))
L.append(kw_pair('Productivity', kw_list(['productivity','automation','workflow','search','note',W(0x6548,0x7387),W(0x81EA,0x52A8,0x5316)])))
L.append(kw_pair('Gaming', kw_list(['game','gaming',W(0x6E38,0x620F)])))
L.append(kw_pair('Research', kw_list(['research','paper','arxiv','benchmark',W(0x7814,0x7A76),W(0x8BBA,0x6587)])))
L.append(kw_pair('Business', kw_list(['enterprise','business',W(0x4F01,0x4E1A),W(0x5546,0x4E1A)])))
L.append('}')
L.append('')

# Write the file - enough to get server running
fp = d / 'rules.py'
fp.write_text('\n'.join(L), 'utf-8')
py_compile.compile(str(fp), doraise=True)
print('rules.py rebuilt (partial), syntax OK')
print(f'Wrote {len(L)} sections')

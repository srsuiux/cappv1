LE'S WORK ON THIS ONE. Automate PowerPoint Alt-Text Captioning Using Python.. so the file will pick the file from the directory/input and do the things and then dump into output one. so i need to use the llm for this i guesss. so use the claude as llm. 

- user will dump the files in the input and then the rest is to extract the image from the ppt, and then understand the context and then parse, and pass it to the large language model and then generate the caption and then bind it to the ppt and then dump it and it will show th eprogress in the logs. and it's not just a one pass flow. and it has to be chunk based as some time the ppt can bve large and we need to parse fist and then do the things. 

- so each ppt have section wise flow. and 
mostly ppt does not have shared image between two differnt sectioins or pages. 

- let's brainstrom. 

- i dont have the claude api access, but i can use the openrouter api. 
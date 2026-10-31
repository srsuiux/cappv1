# Example file

`sample.pptx` is a three-slide deck with a picture, a table and a chart, and no alt text on any of them. Try cappv1 on it without using one of your own files:

```
cp examples/sample.pptx ~/cappv1/input/
cappv1          # then type /run
```

If you run cappv1 from a cloned copy of the project, copy it into that copy's `input` folder instead. The finished copy appears in a new folder inside `output`, and your original stays as it is.

Slide text and notes are sent to your chosen AI service as context, like any deck. Nothing in this one is private.

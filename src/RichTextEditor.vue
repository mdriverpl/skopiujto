<script setup>
import { computed, ref, watch } from 'vue'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import { TextStyle, FontFamily, FontSize, Color } from '@tiptap/extension-text-style'
import TextAlign from '@tiptap/extension-text-align'
import { Bold, Italic, Underline, Strikethrough, AlignLeft, AlignCenter, AlignRight, AlignJustify, List, ListOrdered, Undo2, Redo2, RemoveFormatting } from 'lucide-vue-next'

const props = defineProps({ modelValue: Object, plainText: { type: String, default: '' }, editable: { type: Boolean, default: true }, label: { type: String, default: 'Treść dokumentu' } })
const emit = defineEmits(['update:modelValue', 'update:plainText'])
const revision = ref(0)
const fonts = ['Inter', 'Arial', 'Calibri', 'Georgia', 'Times New Roman', 'Verdana', 'Courier New']
const sizes = ['10px', '12px', '14px', '16px', '18px', '20px', '24px', '32px', '48px', '64px']
function plainDocument(text) {
  return { type: 'doc', content: text.split('\n').map(line => ({ type: 'paragraph', ...(line ? { content: [{ type: 'text', text: line }] } : {}) })) }
}
function cleanPastedHTML(html) {
  const document = new DOMParser().parseFromString(html, 'text/html')
  for (const element of document.querySelectorAll('[style]')) {
    const font = element.style.fontFamily.split(',')[0].trim().replace(/['"]/g, '')
    element.style.fontFamily = fonts.includes(font) ? font : ''
    const size = element.style.fontSize
    if (!/^\d+(?:\.\d+)?(?:px|pt)$/.test(size) || parseFloat(size) < 8 || parseFloat(size) > 72) element.style.fontSize = ''
    if (!/^(#[0-9a-f]{3}(?:[0-9a-f]{3})?|rgb\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\))$/i.test(element.style.color)) element.style.color = ''
  }
  return document.body.innerHTML
}
const editor = useEditor({
  extensions: [StarterKit.configure({ link: false, code: false, codeBlock: false, heading: { levels: [1, 2, 3] } }), TextStyle, FontFamily, FontSize, Color, TextAlign.configure({ types: ['heading', 'paragraph'] })],
  content: props.modelValue || plainDocument(props.plainText), editable: props.editable,
  editorProps: { transformPastedHTML: cleanPastedHTML, attributes: { role: 'textbox', 'aria-label': props.label, 'aria-multiline': 'true', spellcheck: 'true' } },
  onUpdate: ({ editor }) => { emit('update:modelValue', editor.getJSON()); emit('update:plainText', editor.getText()); revision.value++ },
  onSelectionUpdate: () => revision.value++,
  onTransaction: () => revision.value++
})
watch(() => props.editable, value => editor.value?.setEditable(value, false))
watch(() => props.modelValue, value => {
  if (editor.value && value && JSON.stringify(editor.value.getJSON()) !== JSON.stringify(value)) editor.value.commands.setContent(value, { emitUpdate: false })
})
const font = computed(() => { revision.value; return editor.value?.getAttributes('textStyle').fontFamily || 'Inter' })
const size = computed(() => { revision.value; return editor.value?.getAttributes('textStyle').fontSize || '16px' })
const color = computed(() => { revision.value; const value = editor.value?.getAttributes('textStyle').color; return /^#[0-9a-f]{6}$/i.test(value || '') ? value : '#25283d' })
const block = computed(() => { revision.value; for (const level of [1, 2, 3]) if (editor.value?.isActive('heading', { level })) return String(level); return 'paragraph' })
const wordCount = computed(() => { revision.value; return editor.value?.getText().trim().split(/\s+/).filter(Boolean).length || 0 })
const marks = [{ name: 'bold', label: 'Pogrubienie (Ctrl+B)', icon: Bold, command: 'toggleBold' }, { name: 'italic', label: 'Kursywa (Ctrl+I)', icon: Italic, command: 'toggleItalic' }, { name: 'underline', label: 'Podkreślenie (Ctrl+U)', icon: Underline, command: 'toggleUnderline' }, { name: 'strike', label: 'Przekreślenie', icon: Strikethrough, command: 'toggleStrike' }]
const alignments = [{ name: 'left', label: 'Wyrównaj do lewej', icon: AlignLeft }, { name: 'center', label: 'Wyśrodkuj', icon: AlignCenter }, { name: 'right', label: 'Wyrównaj do prawej', icon: AlignRight }, { name: 'justify', label: 'Wyjustuj', icon: AlignJustify }]
function run(command) { editor.value?.chain().focus()[command]().run() }
function changeBlock(value) { const chain = editor.value?.chain().focus(); if (value === 'paragraph') chain?.setParagraph().run(); else chain?.setHeading({ level: Number(value) }).run() }
</script>

<template>
  <div class="rich-editor" :class="{ readonly: !editable }" :data-revision="revision">
    <div v-if="editable && editor" class="formatting-toolbar" role="toolbar" aria-label="Formatowanie tekstu">
      <div class="toolbar-group"><select :value="block" aria-label="Styl akapitu" @change="changeBlock($event.target.value)"><option value="paragraph">Tekst</option><option value="1">Nagłówek 1</option><option value="2">Nagłówek 2</option><option value="3">Nagłówek 3</option></select><select :value="font" aria-label="Czcionka" @change="editor.chain().focus().setFontFamily($event.target.value).run()"><option v-if="!fonts.includes(font)" :value="font">{{ font }}</option><option v-for="item in fonts" :key="item" :style="{ fontFamily: item }">{{ item }}</option></select><select class="size-select" :value="size" aria-label="Rozmiar czcionki" @change="editor.chain().focus().setFontSize($event.target.value).run()"><option v-if="!sizes.includes(size)" :value="size">{{ size }}</option><option v-for="item in sizes" :key="item" :value="item">{{ item.replace('px', '') }}</option></select></div>
      <div class="toolbar-group"><button v-for="mark in marks" :key="mark.name" type="button" :title="mark.label" :aria-label="mark.label" :aria-pressed="editor.isActive(mark.name)" @mousedown.prevent @click="run(mark.command)"><component :is="mark.icon" :size="16" /></button><label class="color-picker" title="Kolor tekstu"><span aria-hidden="true" :style="{ borderColor: color }">A</span><input type="color" :value="color" aria-label="Kolor tekstu" @input="editor.chain().focus().setColor($event.target.value).run()" /></label><button type="button" title="Usuń formatowanie zaznaczenia" aria-label="Usuń formatowanie zaznaczenia" @mousedown.prevent @click="editor.chain().focus().unsetAllMarks().clearNodes().unsetTextAlign().run()"><RemoveFormatting :size="16" /></button></div>
      <div class="toolbar-group"><button v-for="align in alignments" :key="align.name" type="button" :aria-label="align.label" :title="align.label" :aria-pressed="editor.isActive({ textAlign: align.name })" @mousedown.prevent @click="editor.chain().focus().setTextAlign(align.name).run()"><component :is="align.icon" :size="16" /></button><button type="button" title="Lista punktowana" aria-label="Lista punktowana" :aria-pressed="editor.isActive('bulletList')" @mousedown.prevent @click="run('toggleBulletList')"><List :size="16" /></button><button type="button" title="Lista numerowana" aria-label="Lista numerowana" :aria-pressed="editor.isActive('orderedList')" @mousedown.prevent @click="run('toggleOrderedList')"><ListOrdered :size="16" /></button></div>
      <div class="toolbar-group history-tools"><button type="button" title="Cofnij (Ctrl+Z)" aria-label="Cofnij zmianę" :disabled="!editor.can().undo()" @mousedown.prevent @click="run('undo')"><Undo2 :size="16" /></button><button type="button" title="Ponów (Ctrl+Y)" aria-label="Ponów zmianę" :disabled="!editor.can().redo()" @mousedown.prevent @click="run('redo')"><Redo2 :size="16" /></button></div>
    </div>
    <div class="paper-area"><EditorContent :editor="editor" class="text-paper" /></div>
    <div v-if="editable" class="editor-count"><span>{{ wordCount }} słów</span><span>Zaznacz tekst, aby zmienić jego formatowanie.</span></div>
  </div>
</template>

<style scoped>
.rich-editor { border: 1px solid var(--border); border-radius: 12px; overflow: hidden; background: var(--theme-surface-soft, #f5f6fa); }
.formatting-toolbar { display: flex; align-items: center; flex-wrap: wrap; gap: 6px 0; padding: 9px 10px; background: var(--surface); border-bottom: 1px solid var(--border); position: sticky; top: 0; z-index: 1; }
.toolbar-group { display: flex; align-items: center; gap: 3px; padding: 0 7px; border-right: 1px solid var(--border); }
.toolbar-group:last-child { border-right: none; }
.toolbar-group button { width: 29px; height: 30px; padding: 0; border: none; border-radius: 5px; color: var(--muted); }
.toolbar-group button[aria-pressed='true'] { color: var(--accent); background: var(--accent-soft); }
.toolbar-group select { border: none; border-radius: 5px; padding: 6px 4px; font-size: 11px; color: var(--secondary); max-width: 130px; }
.size-select { width: 52px; }
.color-picker { position: relative; width: 29px; height: 30px; display: flex; align-items: center; justify-content: center; cursor: pointer; }
.color-picker span { font-size: 14px; font-weight: 600; line-height: 17px; border-bottom: 3px solid; }
.color-picker input { position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0; cursor: pointer; }
.color-picker:focus-within { outline: 2px solid var(--focus-ring); border-radius: 5px; }
.paper-area { padding: 24px; }
.text-paper { background: var(--surface); max-width: 800px; margin: 0 auto; box-shadow: 0 3px 14px #25283d08; border: 1px solid var(--border); }
.text-paper :deep(.tiptap) { min-height: 400px; padding: 40px 46px; outline: none; font-family: Inter, sans-serif; font-size: 16px; line-height: 1.7; color: var(--text); overflow-wrap: anywhere; white-space: pre-wrap; }
.text-paper :deep(.tiptap > :first-child) { margin-top: 0; }
.text-paper :deep(.tiptap > :last-child) { margin-bottom: 0; }
.text-paper :deep(p) { margin: 0 0 12px; }
.text-paper :deep(h1) { font-size: 28px; margin: 22px 0 14px; letter-spacing: -.5px; }
.text-paper :deep(h2) { font-size: 22px; margin: 20px 0 12px; }
.text-paper :deep(h3) { font-size: 18px; margin: 18px 0 10px; }
.text-paper :deep(ul), .text-paper :deep(ol) { padding-left: 24px; }
.text-paper :deep(li p) { margin-bottom: 4px; }
.text-paper :deep(blockquote) { border-left: 3px solid var(--theme-border, #cfc5ee); padding-left: 16px; margin-left: 0; color: var(--secondary); }
.text-paper :deep(hr) { border: none; border-top: 1px solid var(--border); margin: 20px 0; }
.editor-count { display: flex; justify-content: space-between; gap: 12px; padding: 10px 15px; font-size: 10px; color: var(--muted); border-top: 1px solid var(--border); background: var(--surface); }
.readonly { border: none; background: transparent; }
.readonly .paper-area { padding: 0; }
.readonly .text-paper { border: none; box-shadow: none; }
.readonly .text-paper :deep(.tiptap) { min-height: 0; padding: 16px 0; }
@media (max-width: 600px) { .paper-area { padding: 12px; } .text-paper :deep(.tiptap) { padding: 24px 20px; min-height: 300px; } .editor-count span:last-child { display: none; } }
</style>

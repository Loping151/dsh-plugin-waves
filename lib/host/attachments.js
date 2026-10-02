// 将 DSH 已接收的附件交给鸣潮服务；读取失败直接报错，让输入框保留附件。
export async function readAttachments(ctx, blocks, signal) {
  const store = ctx.get('attachments')
  const images = []
  const files = (blocks || []).filter((block) => block.type === 'file')
  if (files.length > 1) throw new Error('鸣潮命令一次只接受一个文件')
  if (blocks?.length && !store) throw new Error('DSH 附件服务不可用')
  let file
  for (const block of blocks || []) {
    if (block.type === 'image') {
      const { data } = await store.readImage(block.attachment, signal)
      images.push('base64://' + Buffer.from(data).toString('base64'))
    } else if (block.type === 'file') {
      const chunks = []
      for await (const chunk of store.readFileStream(block.attachment, signal)) {
        chunks.push(Buffer.from(chunk))
      }
      file = {
        file_name: block.attachment.name,
        file_data: Buffer.concat(chunks).toString('base64'),
      }
    }
  }
  return { images, ...file }
}

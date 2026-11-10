// Run asset conversion on a permitted Linux VM, never on the MacBook.
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
const root = fileURLToPath(new URL('..', import.meta.url));
if (process.platform !== 'linux') throw Error('Trailer conversion requires a Linux VM. Do not run ffmpeg on the MacBook.');
const input = join(root, 'docs/aunx-decompose-trailer.gif');
const output = file => join(root, 'website/assets', file);
const run = args => execFileSync('ffmpeg', args, { stdio: 'inherit' });
run(['-y', '-i', input, '-frames:v', '1', output('trailer-poster.png')]);
run(['-y', '-i', input, '-vf', 'fps=24,scale=960:-2:flags=lanczos', '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '23', '-movflags', '+faststart', output('trailer.mp4')]);
run(['-y', '-i', input, '-vf', 'fps=24,scale=960:-2:flags=lanczos', '-an', '-c:v', 'libvpx-vp9', '-crf', '35', '-b:v', '0', output('trailer.webm')]);
console.log('Prepared local silent MP4, WebM and PNG. Rebuild and check both modes.');

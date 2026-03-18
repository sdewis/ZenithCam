import moderngl
import numpy as np
import cv2
import logging
import struct

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Renderer")

class Renderer:
    def __init__(self, output_width=1280, output_height=720):
        """
        Initializes the hardware-accelerated renderer using ModernGL.
        """
        self.width = output_width
        self.height = output_height
        self.blur_mode = 1 # Default to Pixelate
        
        # 1. Create Context
        self.use_cpu = False
        try:
            self.ctx = moderngl.create_context(standalone=True, backend='egl')
            logger.info("ModernGL Context created (Standalone - EGL).")
        except Exception as e:
            logger.warning(f"Failed to create EGL context: {e}, falling back to default.")
            try:
                self.ctx = moderngl.create_context(standalone=True)
                logger.info("ModernGL Context created (Standalone).")
            except Exception as e2:
                logger.error(f"Failed to create ModernGL context: {e2}. Falling back to CPU rendering.")
                self.use_cpu = True

        if self.use_cpu:
            return

        # 2. Create Framebuffer
        self.fbo = self.ctx.simple_framebuffer((self.width, self.height))
        self.fbo.use()
        
        # 3. Compile Shaders
        self.prog = self.ctx.program(
            vertex_shader="""
                #version 330
                in vec2 in_vert;
                in vec2 in_texcoord;
                out vec2 v_texcoord;
                uniform vec4 crop_rect; // (x, y, w, h) normalized
                void main() {
                    gl_Position = vec4(in_vert, 0.0, 1.0);
                    v_texcoord = vec2(crop_rect.x + (in_texcoord.x * crop_rect.z),
                                      crop_rect.y + (in_texcoord.y * crop_rect.w));
                }
            """,
            fragment_shader="""
                #version 330
                uniform sampler2D Texture;
                uniform int blur_mode;
                uniform vec4 blur_boxes[10];
                uniform int num_boxes;
                in vec2 v_texcoord;
                out vec4 f_color;

                bool is_inside_box(vec2 uv, vec4 box) {
                    return (uv.x >= box.x && uv.x <= box.x + box.z &&
                            uv.y >= box.y && uv.y <= box.y + box.w);
                }

                void main() {
                    bool blur = false;
                    for (int i = 0; i < num_boxes; i++) {
                        if (is_inside_box(v_texcoord, blur_boxes[i])) {
                            blur = true;
                            break;
                        }
                    }
                    
                    if (blur) {
                        if (blur_mode == 1) { // Pixelate
                            vec2 size = vec2(50.0, 50.0);
                            vec2 uv = floor(v_texcoord * size) / size;
                            f_color = texture(Texture, uv);
                        } else { // Gaussian-ish
                            vec4 color = vec4(0.0);
                            float blur_radius = 0.005;
                            float count = 0.0;
                            for(float x = -2.0; x <= 2.0; x += 1.0) {
                                for(float y = -2.0; y <= 2.0; y += 1.0) {
                                    color += texture(Texture, v_texcoord + vec2(x, y) * blur_radius);
                                    count += 1.0;
                                }
                            }
                            f_color = color / count;
                        }
                    } else {
                        f_color = texture(Texture, v_texcoord);
                    }
                }
            """
        )
        
        vertices = np.array([
            -1.0, -1.0, 0.0, 0.0,
             1.0, -1.0, 1.0, 0.0,
            -1.0,  1.0, 0.0, 1.0,
             1.0,  1.0, 1.0, 1.0,
        ], dtype='f4')
        
        self.vbo = self.ctx.buffer(vertices.tobytes())
        self.vao = self.ctx.simple_vertex_array(self.prog, self.vbo, 'in_vert', 'in_texcoord')
        self.texture = None

    def set_config(self, config):
        """Sets renderer configuration based on performance tier."""
        self.blur_mode = 2 if config.get("blur_type") == "gaussian" else 1

    def _render_cpu(self, frame_rgb, crop_rect, blur_boxes):
        height, width = frame_rgb.shape[:2]
        x, y, w, h = [int(v) for v in crop_rect]
        
        x = max(0, min(x, width - 1))
        y = max(0, min(y, height - 1))
        w = max(1, min(w, width - x))
        h = max(1, min(h, height - y))

        cropped = frame_rgb[y:y+h, x:x+w].copy()
        
        if blur_boxes:
            for (bx, by, bw, bh) in blur_boxes:
                bx, by, bw, bh = int(bx) - x, int(by) - y, int(bw), int(bh)
                ix1, iy1 = max(0, bx), max(0, by)
                ix2, iy2 = min(w, bx + bw), min(h, by + bh)
                
                if ix1 < ix2 and iy1 < iy2:
                    roi = cropped[iy1:iy2, ix1:ix2]
                    if self.blur_mode == 1:
                        small = cv2.resize(roi, (max(1, (ix2-ix1)//15), max(1, (iy2-iy1)//15)), interpolation=cv2.INTER_LINEAR)
                        roi = cv2.resize(small, (ix2-ix1, iy2-iy1), interpolation=cv2.INTER_NEAREST)
                    else:
                        roi = cv2.GaussianBlur(roi, (51, 51), 0)
                    cropped[iy1:iy2, ix1:ix2] = roi

        return cv2.resize(cropped, (self.width, self.height), interpolation=cv2.INTER_LINEAR)

    def render(self, frame_rgb, crop_rect, blur_boxes):
        """Renders the frame with zoom and blur."""
        if getattr(self, 'use_cpu', False):
            return self._render_cpu(frame_rgb, crop_rect, blur_boxes)

        height, width = frame_rgb.shape[:2]
        
        if self.texture is None or self.texture.size != (width, height):
            if self.texture: self.texture.release()
            self.texture = self.ctx.texture((width, height), 3, frame_rgb.tobytes())
        else:
            self.texture.write(frame_rgb.tobytes())
            
        self.texture.use()
        self.prog['crop_rect'].value = (crop_rect[0]/width, crop_rect[1]/height, crop_rect[2]/width, crop_rect[3]/height)
        self.prog['blur_mode'].value = self.blur_mode
        
        norm_boxes = []
        for (bx, by, bw, bh) in blur_boxes[:10]:
            norm_boxes.append((bx/width, by/height, bw/width, bh/height))
            
        flat_boxes = [coord for box in norm_boxes for coord in box]
        while len(flat_boxes) < 40: flat_boxes.append(0.0)
        
        if 'blur_boxes' in self.prog:
            self.prog['blur_boxes'].write(struct.pack('40f', *flat_boxes))
        self.prog['num_boxes'].value = len(norm_boxes)

        self.fbo.clear()
        self.vao.render(moderngl.TRIANGLE_STRIP)
        return np.frombuffer(self.fbo.read(components=3), dtype=np.uint8).reshape((self.height, self.width, 3))

    def release(self):
        """Releases all ModernGL resources."""
        try:
            if self.texture:
                self.texture.release()
                self.texture = None
            if hasattr(self, 'vao') and self.vao:
                self.vao.release()
            if hasattr(self, 'vbo') and self.vbo:
                self.vbo.release()
            if hasattr(self, 'prog') and self.prog:
                self.prog.release()
            if hasattr(self, 'fbo') and self.fbo:
                self.fbo.release()
            if hasattr(self, 'ctx') and self.ctx:
                self.ctx.release()
            logger.info("ModernGL resources released successfully.")
        except Exception as e:
            logger.error(f"Error releasing ModernGL resources: {e}")


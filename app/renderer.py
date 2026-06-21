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
        self.blur_mode = 1  # Default to Pixelate

        # 1. Create Context
        try:
            self.ctx = moderngl.create_context(standalone=True)
            logger.info("ModernGL Context created (Standalone).")
        except Exception as e:
            logger.error(f"Failed to create ModernGL context: {e}")
            raise

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
            """,
        )

        vertices = np.array(
            [
                -1.0,
                -1.0,
                0.0,
                0.0,
                1.0,
                -1.0,
                1.0,
                0.0,
                -1.0,
                1.0,
                0.0,
                1.0,
                1.0,
                1.0,
                1.0,
                1.0,
            ],
            dtype="f4",
        )

        self.vbo = self.ctx.buffer(vertices.tobytes())
        self.vao = self.ctx.simple_vertex_array(
            self.prog, self.vbo, "in_vert", "in_texcoord"
        )
        self.texture = None
        self._released = False

    def __del__(self):
        """Safety net to release resources when object is garbage collected."""
        if not self._released:
            self.release()

    def release(self):
        """Safely releases all GPU resources in reverse creation order."""
        if self._released:
            return

        logger.info("Releasing GPU resources...")

        # Release texture (if exists)
        try:
            if self.texture is not None:
                self.texture.release()
                self.texture = None
        except Exception as e:
            logger.error(f"Failed to release texture: {e}")

        # Release VAO
        try:
            if self.vao is not None:
                self.vao.release()
                self.vao = None
        except Exception as e:
            logger.error(f"Failed to release VAO: {e}")

        # Release VBO
        try:
            if self.vbo is not None:
                self.vbo.release()
                self.vbo = None
        except Exception as e:
            logger.error(f"Failed to release VBO: {e}")

        # Release shader program
        try:
            if self.prog is not None:
                self.prog.release()
                self.prog = None
        except Exception as e:
            logger.error(f"Failed to release shader program: {e}")

        # Release framebuffer
        try:
            if self.fbo is not None:
                self.fbo.release()
                self.fbo = None
        except Exception as e:
            logger.error(f"Failed to release framebuffer: {e}")

        # Release context
        try:
            if self.ctx is not None:
                self.ctx.release()
                self.ctx = None
        except Exception as e:
            logger.error(f"Failed to release context: {e}")

        self._released = True
        logger.info("All GPU resources released successfully.")

    def set_config(self, config):
        """Sets renderer configuration based on performance tier."""
        self.blur_mode = 2 if config.get("blur_type") == "gaussian" else 1

    def render(self, frame_rgb, crop_rect, blur_boxes):
        """Renders the frame with zoom and blur."""
        height, width = frame_rgb.shape[:2]

        if self.texture is None or self.texture.size != (width, height):
            if self.texture:
                self.texture.release()
            self.texture = self.ctx.texture((width, height), 3, frame_rgb.tobytes())
        else:
            self.texture.write(frame_rgb.tobytes())

        self.texture.use()
        self.prog["crop_rect"].value = (
            crop_rect[0] / width,
            crop_rect[1] / height,
            crop_rect[2] / width,
            crop_rect[3] / height,
        )
        self.prog["blur_mode"].value = self.blur_mode

        norm_boxes = []
        for bx, by, bw, bh in blur_boxes[:10]:
            norm_boxes.append((bx / width, by / height, bw / width, bh / height))

        flat_boxes = [coord for box in norm_boxes for coord in box]
        while len(flat_boxes) < 40:
            flat_boxes.append(0.0)

        if "blur_boxes" in self.prog:
            self.prog["blur_boxes"].write(struct.pack("40f", *flat_boxes))
        self.prog["num_boxes"].value = len(norm_boxes)

        self.fbo.clear()
        self.vao.render(moderngl.TRIANGLE_STRIP)
        return np.frombuffer(self.fbo.read(components=3), dtype=np.uint8).reshape(
            (self.height, self.width, 3)
        )

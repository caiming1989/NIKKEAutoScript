import os
import cv2
import numpy as np
from module.base.timer import Timer
from module.logger import logger
from module.daemon.assets import MAIN_STORY_MAP_CLOSE, MAIN_STORY_MARK_IN, MAIN_STORY_MARK_OUT, MAIN_STORY_NORMAL, TEMPLATE_SWITCH
from module.daemon.daemon_base import DaemonBase
from module.event.assets import FIELD_CHANGE
from module.simulation_room.assets import AUTO_BURST, AUTO_SHOOT, END_FIGHTING, FIGHT, PAUSE
from module.tribe_tower.assets import NEXT_STAGE
from module.ui.assets import FIGHT_QUICKLY_ENABLE, SKIP, SURFACE_CHECK
from module.ui.ui import UI


class SemiCombat(UI, DaemonBase):
    def run(self):
        timeout = Timer(600, count=10)
        click_timer = Timer(0.3)
        monster_timer = Timer(5)
        switch_timer = Timer(2)
        self._post_battle = True

        while 1:
            self.device.screenshot()

            # 关闭地图
            if (
                (self.config.SemiCombat_MainStoryMark or self.config.SemiCombat_SearchMonster)
                and click_timer.reached()
                and self.appear_then_click(MAIN_STORY_MAP_CLOSE, offset=30, interval=1)
            ):
                click_timer.reset()
                continue

            # 快速战斗
            if (
                self.config.SemiCombat_FightQuickly
                and click_timer.reached()
                and self.appear_then_click(FIGHT_QUICKLY_ENABLE, threshold=20, interval=2)
            ):
                click_timer.reset()
                continue

            # 进入战斗
            if click_timer.reached() and self.appear_then_click(FIGHT, threshold=20, interval=2):
                self._post_battle = True
                click_timer.reset()
                continue

            # 战斗结束后优先找机关踩（机关通常在野怪旁边，需要先踩机关开门才能继续前进）
            if self._post_battle and click_timer.reached() and switch_timer.reached():
                in_campaign = self.is_in_campaign()
                fq_visible = self.appear(FIGHT_QUICKLY_ENABLE, threshold=20)
                fight_visible = self.appear(FIGHT, threshold=20)
                logger.info(
                    f"PostBattle switch check: is_in_campaign={in_campaign}, "
                    f"FIGHT_QUICKLY={fq_visible}, FIGHT={fight_visible}"
                )
                if not fq_visible and not fight_visible:
                    if self._find_and_step_switch():
                        self._post_battle = False
                        click_timer.reset()
                        continue
                    # 没找到机关，解除 post_battle 状态，恢复正常感叹号跟随
                    self._post_battle = False

            # 主线剧情图标，界面外
            if (
                (self.config.SemiCombat_MainStoryMark or self.config.SemiCombat_SearchMonster)
                and click_timer.reached()
                and self.is_in_campaign()
            ):
                if self.appear(MAIN_STORY_MARK_OUT, offset=30, threshold=0.85, interval=5, static=False):
                    cx, cy = MAIN_STORY_MARK_OUT.location
                    if 200 <= cx <= 520 and 300 <= cy <= 900:
                        logger.info(f"MAIN_STORY_MARK_OUT matched near center (player): ({cx:.1f}, {cy:.1f}). Ignoring it.")
                        if MAIN_STORY_MARK_OUT.name in self.interval_timer:
                            self.interval_timer[MAIN_STORY_MARK_OUT.name].clear()
                    else:
                        self.device.click(MAIN_STORY_MARK_OUT)
                        click_timer.reset()
                        continue

            # 主线剧情图标，界面内
            if (
                (self.config.SemiCombat_MainStoryMark or self.config.SemiCombat_SearchMonster)
                and click_timer.reached()
                and not self.appear(FIGHT_QUICKLY_ENABLE, threshold=20)
                and not self.appear(FIGHT, threshold=20)
                and self.is_in_campaign()
            ):
                if self.appear_with_scale(MAIN_STORY_MARK_IN, scale_range=(0.7, 1.2), interval=5):
                    cx, cy = MAIN_STORY_MARK_IN.location
                    if 330 <= cx <= 390 and 430 <= cy <= 680:
                        logger.info(f"MAIN_STORY_MARK_IN matched near player: ({cx:.1f}, {cy:.1f}). Clicking it directly without offset.")
                        self.device.click(MAIN_STORY_MARK_IN, click_offset=(0, 0))
                        click_timer.reset()
                        continue
                    else:
                        self.device.click(MAIN_STORY_MARK_IN, click_offset=(0, 130))
                        click_timer.reset()
                        continue

            # 寻找野怪并前往；清完怪后自动寻找附近机关
            if (
                self.config.SemiCombat_SearchMonster
                and click_timer.reached()
                and monster_timer.reached()
            ):
                in_campaign = self.is_in_campaign()
                fq_enable = self.appear(FIGHT_QUICKLY_ENABLE, threshold=20)
                fight_enable = self.appear(FIGHT, threshold=20)
                logger.info(f"SearchMonster Check: is_in_campaign={in_campaign}, FIGHT_QUICKLY_ENABLE={fq_enable}, FIGHT={fight_enable}")
                if in_campaign and not fq_enable and not fight_enable:
                    # 如果主线感叹号已在角色附近，优先等待主线交互，不寻怪
                    if self.appear_with_scale(MAIN_STORY_MARK_IN, scale_range=(0.7, 1.2)):
                        cx, cy = MAIN_STORY_MARK_IN.location
                        if 330 <= cx <= 390 and 430 <= cy <= 680:
                            logger.info("MAIN_STORY_MARK_IN is near player. Skipping SearchMonster to prioritize story interaction.")
                            monster_timer.reset()
                            continue

                    coord = self.find_monster_coordinate()
                    if coord:
                        cx, cy = coord
                        self.device.click_minitouch(cx, cy)
                        logger.info(f"Walking to monster at {(cx, cy)}")
                        monster_timer.reset()
                        click_timer.reset()
                        continue
                    else:
                        # 没有野怪了，检查附近是否有机关需要踩
                        if self._find_and_step_switch():
                            monster_timer.reset()
                            click_timer.reset()
                            continue
                        logger.info("No monster or switch detected on campaign map.")
                else:
                    logger.info("Skipping SearchMonster because not in campaign map or fight buttons are visible.")
                monster_timer.reset()

            # 跳过剧情
            if (
                self.config.SemiCombat_SkipStory
                and click_timer.reached()
                and self.appear_then_click(SKIP, offset=(150, 10), interval=1)
            ):
                click_timer.reset()
                continue

            # 下一关卡
            if click_timer.reached() and self.appear_then_click(NEXT_STAGE, offset=(100, 30), interval=2):
                click_timer.reset()
                continue

            if click_timer.reached() and self.appear_then_click(END_FIGHTING, offset=30):
                self._post_battle = True
                click_timer.reset()
                continue

            # 前往区域
            if click_timer.reached() and self.appear_then_click(FIELD_CHANGE, offset=30, interval=1):
                click_timer.reset()
                continue

            # 自动射击
            if click_timer.reached() and self.appear_then_click(AUTO_SHOOT, offset=10, threshold=0.9, interval=5):
                click_timer.reset()
                continue
            if click_timer.reached() and self.appear_then_click(AUTO_BURST, offset=10, threshold=0.9, interval=5):
                click_timer.reset()
                continue

            # 红圈
            if self.config.Optimization_AutoRedCircle and self.appear(PAUSE, offset=10):
                if self.handle_red_circles():
                    click_timer.reset()
                    continue

            if not timeout.started():
                timeout.start()
            if timeout.reached():
                break
            else:
                timeout.clear()

    def _find_and_step_switch(self):
        """
        多尺度匹配寻找地面机关，找到则点击前往踩踏。
        机关通常在野怪附近，清完怪后触发。
        """
        sim, button = TEMPLATE_SWITCH.match_result_with_scale(
            self.device.image, scale_range=(0.5, 1.4), scale_step=0.05, name='SWITCH'
        )
        if sim > 0.70:
            cx, cy = button.location
            # 排除屏幕边缘（UI 区域）和角色脚下正中心的误匹配
            if cy < 100 or cy > 1050 or cx < 30 or cx > 690:
                logger.info(f"Switch matched at ({cx}, {cy}) sim={sim:.3f} but in UI area, skipping.")
                return False
            self.device.click_minitouch(cx, cy)
            logger.info(f"Stepping on switch at ({cx}, {cy}), similarity={sim:.3f}")
            return True
        else:
            logger.debug(f"Switch not found (best_sim={sim:.3f})")
            return False

    def is_in_campaign(self):
        """
        判断是否在战役大地图上（兼容普通模式和困难模式）
        """
        return self.appear(MAIN_STORY_NORMAL, offset=30) or self.appear(SURFACE_CHECK, offset=30)

    def find_monster_coordinate(self):
        """
        通过 OpenCV 提取红色/橙色以及蓝色高亮光圈，寻找地图上的野怪中心点坐标，排除玩家自身。
        """
        image = self.device.image
        if image is None:
            logger.warning("find_monster_coordinate: self.device.image is None")
            return None

        # 转换到 HSV 空间（因为 self.device.image 为 RGB 格式，需使用 COLOR_RGB2HSV 防止红蓝通道颠倒）
        hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)

        # 设定只匹配高饱和度、高亮度红霓虹光圈的阈值，防止背景中的锈铁（橙色）、黄泥地等低饱和度温色调物体被误判
        s_min = 80
        v_min = 80

        # 红色范围（分为两段），将 Hue 范围限制在红至微橙红区间（0-12 与 168-180），避开黄褐色及锈铁色（Hue > 12）
        lower_red1 = np.array([0, s_min, v_min])
        upper_red1 = np.array([12, 255, 255])
        lower_red2 = np.array([168, s_min, v_min])
        upper_red2 = np.array([180, 255, 255])

        mask_red1 = cv2.inRange(hsv, lower_red1, upper_red1)
        mask_red2 = cv2.inRange(hsv, lower_red2, upper_red2)
        mask = cv2.bitwise_or(mask_red1, mask_red2)

        # 形态学去噪
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        mask_cleaned = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask_cleaned = cv2.morphologyEx(mask_cleaned, cv2.MORPH_OPEN, kernel)

        # 连通域统计
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask_cleaned, connectivity=8)
        candidates = []
        logger.info(f"find_monster_coordinate: Found {num_labels - 1} raw connected components after morphological filtering")
        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            cx, cy = centroids[i]

            # 提升最小面积限制至 100 像素，过滤掉残余的微小地面背景噪点和灭火器等小道具
            if 100 < area < 25000:
                # 纵向范围收窄到 1050，彻底过滤底部状态栏/章节信息/返回按钮等 UI 区域
                if 120 < cy < 1050 and 50 < cx < 670:
                    # 针对水平横排站立的多名玩家角色及其横向拉长的椭圆形选择光圈，采用矩形边界过滤：
                    # 屏幕中心 (360, 640)，横向排除半径 220 像素 (140-580)，纵向排除半径 160 像素 (480-800)
                    if 140 <= cx <= 580 and 400 <= cy <= 800:
                        logger.info(f"Component {i}: area={area}, coord=({cx:.1f}, {cy:.1f}) (Excluded as Player Team)")
                        continue
                    dist_to_center = ((cx - 360) ** 2 + (cy - 640) ** 2) ** 0.5
                    candidates.append((cx, cy, dist_to_center, area))
                    logger.info(f"Component {i}: area={area}, coord=({cx:.1f}, {cy:.1f}), dist={dist_to_center:.1f} (Added as Candidate)")
                else:
                    logger.info(f"Component {i}: area={area}, coord=({cx:.1f}, {cy:.1f}) (Excluded by position boundary)")
            else:
                logger.info(f"Component {i}: area={area}, coord=({cx:.1f}, {cy:.1f}) (Excluded by area size limits)")

        if candidates:
            # 按距离中心最近排序，选择最近的野怪
            candidates.sort(key=lambda x: x[2])
            best_cx, best_cy, _, _ = candidates[0]
            logger.info(f"Detected {len(candidates)} monster candidate light circles. Nearest at ({best_cx:.1f}, {best_cy:.1f})")
            return int(best_cx), int(best_cy)

        # 没检测到时，将去噪后的 mask 保存至 log/debug_monster_mask.png，原图保存至 log/debug_monster_image.png 便于诊断
        try:
            debug_path = "log/debug_monster_mask.png"
            debug_img_path = "log/debug_monster_image.png"
            os.makedirs("log", exist_ok=True)
            cv2.imwrite(debug_path, mask_cleaned)
            cv2.imwrite(debug_img_path, image)
            logger.info(f"Saved debug mask image to {debug_path} and original image to {debug_img_path}")
        except Exception as e:
            logger.warning(f"Failed to save debug images: {e}")

        return None


if __name__ == '__main__':
    b = SemiCombat('nkas', task='SemiCombat')
    b.run()

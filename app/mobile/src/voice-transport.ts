import { PermissionsAndroid, Platform, NativeModules } from "react-native";
import { AudioSession, AndroidAudioTypePresets } from "@livekit/react-native";
import { ConnectionState, Room, RoomEvent } from "livekit-client";

export type Access = {
  url: string;
  token: string;
  simulated: boolean;
  id: string;
};
export class VoiceTransport {
  private room: Room | null = null;
  private generation = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  async connect(access: Access, status: (state: string) => void) {
    const generation = ++this.generation;
    const current = () => {
      if (generation !== this.generation) throw new Error("Call canceled.");
    };
    if (access.simulated) {
      status("simulated");
      return;
    }
    if (!access.url.startsWith("wss://") || !access.token)
      throw new Error("Secure voice access is unavailable.");
    if (Platform.OS === "android") {
      const permission = await PermissionsAndroid.request(
        PermissionsAndroid.PERMISSIONS.RECORD_AUDIO,
      );
      if (permission !== PermissionsAndroid.RESULTS.GRANTED)
        throw new Error(
          "Microphone permission was denied. No audio is being sent.",
        );
    }
    current();
    await AudioSession.configureAudio({android:{preferredOutputList:["bluetooth","headset","earpiece","speaker"],audioTypeOptions:AndroidAudioTypePresets.communication}});
    await AudioSession.startAudioSession();
    current();
    const room = new Room({ adaptiveStream: true });
    this.room = room;
    const ready = () => {
      const agent = [...room.remoteParticipants.values()].some(
        (p) => p.isAgent,
      );
      if (
        room.state === ConnectionState.Connected &&
        agent &&
        room.localParticipant.isMicrophoneEnabled
      ) {
        if (this.timer) clearTimeout(this.timer);
        status("connected");
      } else status("waiting_for_agent");
    };
    room.on(RoomEvent.ParticipantConnected, ready);
    room.on(RoomEvent.ParticipantDisconnected, () => {
      status("waiting_for_agent");
      if(this.timer) clearTimeout(this.timer);
      this.timer=setTimeout(() => {status("failed");void this.close();},45000);
    });
    room.on(RoomEvent.Reconnecting, () => status("reconnecting"));
    room.on(RoomEvent.Reconnected, ready);
    room.on(RoomEvent.Disconnected, () => status("ended"));
    try {
      status("connecting");
      this.timer = setTimeout(() => {
        status("failed");
        void this.close();
      }, 45000);
      await room.connect(access.url, access.token);
      current();
      await room.localParticipant.setMicrophoneEnabled(true);
      await NativeModules.YggdrasCalls?.startAudioService();
      ready();
    } catch {
      await this.close();
      throw new Error(
        "Voice could not connect. Your call history is preserved; try again.",
      );
    }
  }
  async mute(value: boolean) {
    await this.room?.localParticipant.setMicrophoneEnabled(!value);
  }
  async speaker(value: boolean) {
    await AudioSession.selectAudioOutput(value ? "speaker" : "earpiece");
  }
  async close() {
    this.generation++;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    const room = this.room;
    this.room = null;
    if (room) {
      room.removeAllListeners();
      await room.disconnect();
    }
    NativeModules.YggdrasCalls?.stopAudioService();
    await AudioSession.stopAudioSession();
  }
}

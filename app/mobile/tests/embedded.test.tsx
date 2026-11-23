import { fireEvent, render, screen } from "@testing-library/react-native";
import { Embedded } from "../src/embedded";

const mockInject = jest.fn();
jest.mock("../src/api", () => ({
  session: () => ({
    origin: "http://127.0.0.1:3300",
    token: "invented-test-token",
  }),
  sessionExpired: jest.fn(),
}));
jest.mock("react-native-webview", () => {
  const React = require("react");
  const { View } = require("react-native");
  return {
    WebView: React.forwardRef((props: object, ref: unknown) => {
      React.useImperativeHandle(ref, () => ({ injectJavaScript: mockInject }));
      return React.createElement(View, { ...props, testID: "embedded-view" });
    }),
  };
});

test("returning to Notes refreshes its catalogue without reloading away an open draft", () => {
  const view = render(<Embedded view="notes" active />);
  expect(mockInject).not.toHaveBeenCalled();
  fireEvent(screen.getByTestId("embedded-view"), "loadEnd");
  view.rerender(<Embedded view="notes" active={false} />);
  view.rerender(<Embedded view="notes" active />);
  expect(mockInject).toHaveBeenCalledTimes(1);
  expect(mockInject.mock.calls[0][0]).toContain("yggdras:foreground");
  expect(mockInject.mock.calls[0][0]).not.toContain("invented-test-token");
  const source = screen.getByTestId("embedded-view").props.source;
  expect(source.method).toBe("POST");
  expect(source.uri).not.toContain("invented-test-token");
});

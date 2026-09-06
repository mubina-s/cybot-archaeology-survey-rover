/*
 * main_GUI_FINAL_PROJECT_READY.c
 *
 * Drop-in replacement for main.c for the CPRE 288 lab project GUI.
 * This file does NOT change movement.c, scan.c, uart-interrupt.c, or any other helper functions.
 * It only makes the top-level command loop GUI friendly.
 *
 * CyBot WiFi: 192.168.1.1   Port: 288
 */

#include "Timer.h"
#include "lcd.h"
#include "open_interface.h"
#include "movement.h"
#include "uart-interrupt.h"
#include "scan.h"

#include <stdio.h>
#include <stdbool.h>
#include <string.h>
#include "driverlib/interrupt.h"

extern int rescan_needed;

/*
 * Sends one easy-to-parse sensor line for the GUI.
 * The GUI can use this for the required bump/cliff/boundary display.
 */
void sendSensorStatus(oi_t *sensor_data)
{
    char buffer[280];
    int bumperSeen;
    int cliffSeen;
    int boundarySeen;

    oi_update(sensor_data);

    bumperSeen = sensor_data->bumpLeft || sensor_data->bumpRight;

    cliffSeen = sensor_data->cliffLeft ||
                sensor_data->cliffFrontLeft ||
                sensor_data->cliffFrontRight ||
                sensor_data->cliffRight ||
                sensor_data->wheelDropLeft ||
                sensor_data->wheelDropRight;

    /*
     * Your movement.c also checks white tape using raw cliff signals.
     * That helper is private inside movement.c, so here boundarySeen uses the
     * normal cliff/wheel-drop danger flags. Emergency handling still happens
     * inside movement.c through emergency_detected().
     */
    boundarySeen = cliffSeen;

    sprintf(buffer,
            "\r\nGUI_SENSOR,bumper=%d,cliff=%d,boundary=%d,"
            "bumpLeft=%d,bumpRight=%d,"
            "cliffLeft=%d,cliffFrontLeft=%d,cliffFrontRight=%d,cliffRight=%d,"
            "wheelDropLeft=%d,wheelDropRight=%d\r\n",
            bumperSeen,
            cliffSeen,
            boundarySeen,
            sensor_data->bumpLeft,
            sensor_data->bumpRight,
            sensor_data->cliffLeft,
            sensor_data->cliffFrontLeft,
            sensor_data->cliffFrontRight,
            sensor_data->cliffRight,
            sensor_data->wheelDropLeft,
            sensor_data->wheelDropRight);

    uart_sendStr(buffer);
}

void sendHelpMenu(void)
{
    uart_sendStr("\r\n================ CYBOT GUI COMMANDS ================\r\n");
    uart_sendStr("S = start / wake / ready\r\n");
    uart_sendStr("1 = forward 10 cm     2 = forward 20 cm\r\n");
    uart_sendStr("3 = forward 30 cm     4 = forward 40 cm\r\n");
    uart_sendStr("5 = backward 10 cm    6 = backward 20 cm\r\n");
    uart_sendStr("7 = left 5 deg        8 = left 10 deg\r\n");
    uart_sendStr("9 = left 45 deg       0 = left 90 deg\r\n");
    uart_sendStr("q = right 5 deg       w = right 10 deg\r\n");
    uart_sendStr("e = right 45 deg      r = right 90 deg\r\n");
    uart_sendStr("t = stop / standby\r\n");
    uart_sendStr("y = 180 scan          u = 360 site scan\r\n");
    uart_sendStr("H = help + sensor status\r\n");
    uart_sendStr("====================================================\r\n");
}

/*
 * One command handler for PuTTY or the Python GUI.
 * Important: this only calls your existing functions. The helper functions
 * in movement.c and scan.c stay the same.
 */
void handleManualCommand(char command, oi_t *sensor_data)
{
    char buffer[80];

    /* Tell the GUI exactly what the CyBot received. */
    sprintf(buffer, "\r\nCOMMAND_RECEIVED:%c\r\n", command);
    uart_sendStr(buffer);

    switch (command)
    {
        /* GUI start / wake command */
        case 'S':
            oi_setWheels(0, 0);
            uart_sendStr("\r\nEVENT:CYBOT_READY\r\n");
            sendSensorStatus(sensor_data);
            break;

        /* Forward movement commands */
        case '1':
            uart_sendStr("\r\nEVENT:MOVE_START,dir=forward,cm=10\r\n");
            move_forward_manual(sensor_data, 100);
            sendSensorStatus(sensor_data);
            break;

        case '2':
            uart_sendStr("\r\nEVENT:MOVE_START,dir=forward,cm=20\r\n");
            move_forward_manual(sensor_data, 200);
            sendSensorStatus(sensor_data);
            break;

        case '3':
            uart_sendStr("\r\nEVENT:MOVE_START,dir=forward,cm=30\r\n");
            move_forward_manual(sensor_data, 300);
            sendSensorStatus(sensor_data);
            break;

        case '4':
            uart_sendStr("\r\nEVENT:MOVE_START,dir=forward,cm=40\r\n");
            move_forward_manual(sensor_data, 400);
            sendSensorStatus(sensor_data);
            break;

        /* Backward movement commands */
        case '5':
            uart_sendStr("\r\nEVENT:MOVE_START,dir=backward,cm=10\r\n");
            move_backward_manual(sensor_data, 100);
            sendSensorStatus(sensor_data);
            break;

        case '6':
            uart_sendStr("\r\nEVENT:MOVE_START,dir=backward,cm=20\r\n");
            move_backward_manual(sensor_data, 200);
            sendSensorStatus(sensor_data);
            break;

        /* Left turns */
        case '7':
            uart_sendStr("\r\nEVENT:TURN_START,dir=left,deg=5\r\n");
            turn_left_manual(sensor_data, 5);
            sendSensorStatus(sensor_data);
            break;

        case '8':
            uart_sendStr("\r\nEVENT:TURN_START,dir=left,deg=10\r\n");
            turn_left_manual(sensor_data, 10);
            sendSensorStatus(sensor_data);
            break;

        case '9':
            uart_sendStr("\r\nEVENT:TURN_START,dir=left,deg=45\r\n");
            turn_left_manual(sensor_data, 45);
            sendSensorStatus(sensor_data);
            break;

        case '0':
            uart_sendStr("\r\nEVENT:TURN_START,dir=left,deg=90\r\n");
            turn_left_manual(sensor_data, 90);
            sendSensorStatus(sensor_data);
            break;

        /* Right turns */
        case 'q':
            uart_sendStr("\r\nEVENT:TURN_START,dir=right,deg=5\r\n");
            turn_right_manual(sensor_data, 5);
            sendSensorStatus(sensor_data);
            break;

        case 'w':
            uart_sendStr("\r\nEVENT:TURN_START,dir=right,deg=10\r\n");
            turn_right_manual(sensor_data, 10);
            sendSensorStatus(sensor_data);
            break;

        case 'e':
            uart_sendStr("\r\nEVENT:TURN_START,dir=right,deg=45\r\n");
            turn_right_manual(sensor_data, 45);
            sendSensorStatus(sensor_data);
            break;

        case 'r':
            uart_sendStr("\r\nEVENT:TURN_START,dir=right,deg=90\r\n");
            turn_right_manual(sensor_data, 90);
            sendSensorStatus(sensor_data);
            break;

        /* Stop / standby */
        case 't':
            oi_setWheels(0, 0);
            uart_sendStr("\r\nEVENT:STOP\r\n");
            uart_sendStr("\r\nEVENT:STANDBY\r\n");
            sendSensorStatus(sensor_data);
            break;

        /* 180 degree scan. scan180() already sends GUI_OBJECT lines. */
        case 'y':
            oi_setWheels(0, 0);
            uart_sendStr("\r\nEVENT:SCAN_COMMAND_ACCEPTED,type=180\r\n");
            scan180();
            sendSensorStatus(sensor_data);
            break;

        /* 360 degree site scan. scan360() already sends scan + turn data. */
        case 'u':
            oi_setWheels(0, 0);
            uart_sendStr("\r\nEVENT:SCAN_COMMAND_ACCEPTED,type=360\r\n");
            scan360(sensor_data);
            sendSensorStatus(sensor_data);
            break;

        /* Help also sends sensor status because uart-interrupt.c currently does not accept lowercase 's'. */
        case 'H':
            sendHelpMenu();
            sendSensorStatus(sensor_data);
            break;

        default:
            uart_sendStr("\r\nEVENT:UNKNOWN_COMMAND\r\n");
            sendHelpMenu();
            break;
    }
}

int main(void)
{
    oi_t *sensor_data;
    unsigned int lastHeartbeatMs = 0;

    timer_init();
    lcd_init();
    uart_interrupt_init();
    scanInit();

    sensor_data = oi_alloc();

    timer_waitMillis(500);
    lcd_printf("Before oi init");
    timer_waitMillis(500);

    oi_init(sensor_data);

    timer_waitMillis(500);
    lcd_printf("GUI Manual Mode");

    command_byte = 0;
    command_flag = 0;
    rescan_needed = 0;

    uart_sendStr("\r\nCYBOT MANUAL MODE READY\r\n");
    uart_sendStr("EVENT:GUI_READY_NO_BLOCKING_WAIT\r\n");
    uart_sendStr("EVENT:CONNECT_OK\r\n");
    sendHelpMenu();
    sendSensorStatus(sensor_data);

    /*
     * Main loop:
     * 1. Emergency sensors are checked first.
     * 2. GUI/base-station commands are handled next.
     * 3. Small heartbeat keeps GUI connection visibly alive.
     */
    while (1)
    {
        oi_update(sensor_data);

        /* Highest priority: sensor emergency. */
        if (emergency_detected(sensor_data))
        {
            oi_setWheels(0, 0);
            sendSensorStatus(sensor_data);
            handle_emergency_stop(sensor_data);
            sendSensorStatus(sensor_data);

            command_flag = 0;
            command_byte = 0;

            uart_sendStr("\r\nEVENT:EMERGENCY_HANDLED\r\n");
            continue;
        }

        /* Next priority: base station / GUI commands. */
        if (command_flag)
        {
            char cmd = command_byte;

            /* Clear first so the interrupt can receive the next command while this command runs. */
            command_flag = 0;
            command_byte = 0;

            handleManualCommand(cmd, sensor_data);
        }

        /* Heartbeat every ~2 seconds so the GUI does not look frozen when idle. */
        if ((timer_getMillis() - lastHeartbeatMs) > 2000)
        {
            lastHeartbeatMs = timer_getMillis();
            uart_sendStr("\r\nEVENT:HEARTBEAT\r\n");
        }
    }
}

/*
 * Copyright (c) 2013-2015 Freescale Semiconductor, Inc.
 * Copyright 2016-2018 NXP
 * All rights reserved.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

#include <cstring>
#include "blfwk/options.h"
#include "blfwk/Logging.h"
#include "blfwk/host_types.h"
#include "blfwk/utils.h"
#include "blfwk/Command.h"
#include "blfwk/SDPCommand.h"
#include "blfwk/UsbHidPeripheral.h"
#include "blfwk/SDPUsbHidPacketizer.h"
#include "blfwk/UartPeripheral.h"
#include "blfwk/SDPUartPacketizer.h"

#if defined(WIN32)
#include "windows.h"
#include "stdafx.h"
#elif defined(LINUX) || defined(MACOSX)
#include "signal.h"
#endif

using namespace blfwk;
using namespace std;

////////////////////////////////////////////////////////////////////////////////
// Variables
////////////////////////////////////////////////////////////////////////////////

//! @brief The tool's name.
const char k_toolName[] = "sdphost";

//! @brief Current version number for the tool.
const char k_version[] = "1.0.0";

//! @brief Copyright string.
const char k_copyright[] = "Copyright (c) 2016 Freescale Semiconductor, Inc.\nAll rights reserved.";

//! @brief Command line option definitions.
static const char *k_optionsDefinition[] = { "?|help", "v|version", "p:port <name>[,<speed>]",
"u?usb [[<vid>,]<pid>]", "V|verbose", "d|debug", "j|json",
"t:timeout <ms>", NULL };

//! @brief Usage text.
const char k_optionUsage[] =
"\nOptions:\n\
  -?/--help                    Show this help\n\
  -v/--version                 Display tool version\n\
  -p/--port <name>[,<speed>]   Connect to target over UART. Specify COM port\n\
                               and optionally baud rate\n\
                                 (default=COM1,115200)\n\
                                 If -b, then port is BusPal port\n\
  -u/--usb [[[<vid>,]<pid>] | [<path>]]\n\
                               Connect to target over USB HID device denoted by\n\
                               vid/pid (default=0x15a2,0x0083) or device path\n\
  -V/--verbose                 Print extra detailed log information\n\
  -d/--debug                   Print really detailed log information\n\
  -j/--json                    Print output in JSON format to aid automation.\n\
                                 The last -V/-d/-j takes precedence.\n\
  -t/--timeout <ms>            Set packet timeout in milliseconds\n\
                                 (default=5000)\n";

//! @brief Trailer usage text that gets appended after the options descriptions.
static const char *usageTrailer = "-- command <args...>";

//! @brief Command usage string.
const char k_commandUsage[] =
"Commands:\n\
  read-register <addr> [<format> [<count> [<file>]]]\n\
                               Read one or more registers at address.\n\
                               Format must be 8, 16, or 32;\n\
                                 default format is 32.\n\
                               Count is number of bytes to read;\n\
                                 default count is sizeof format\n\
                                 (i.e. one register).\n\
                               Output file is binary;\n\
                                 default is hex display on stdout.\n\
  write-register <addr> <format> <data>\n\
                               Write one register at address.\n\
                               Format must be 8, 16, or 32.\n\
                               Data is data value to write.\n\
  write-file <addr> <file> [<count>]\n\
                               Write file at address.\n\
                               Count is size of data to write in bytes;\n\
                                 size of file will be used by default.\n\
  error-status                 Read error status of last command.\n\
  dcd-write <addr> <file>      Send DCD table from file.\n\
                                 <addr> must point to a valid\n\
                                   temporary storage area.\n\
  skip-dcd-header              Ignore DCD table in image.\n\
  jump-address <addr>          Jump to entry point of image\n\
                                   with IVT at specified address.\n\
\n";

/*!
* \brief Class that encapsulates the sdp tool.
*
* A single global logger instance is created during object construction. It is
* never freed because we need it up to the last possible minute, when an
* exception could be thrown.
*/
class SDPHost
{
public:
    /*!
    * Constructor.
    *
    * Creates the singleton logger instance.
    */
    SDPHost(int argc, char *argv[])
        : m_argc(argc)
        , m_argv(argv)
        , m_cmdv()
        , m_comPort("COM1")
        , m_comSpeed(115200)
        , m_logger(NULL)
        , m_useUsb(false)
        , m_useUart(false)
        , m_usbVid(UsbHidPeripheral::kDefault_Vid)
        , m_usbPid(UsbHidPeripheral::kK32H_Pid)
        , m_packetTimeoutMs(5000)
    {
        // create logger instance
        m_logger = new StdoutLogger();
        m_logger->setFilterLevel(Logger::kInfo);
        Log::setLogger(m_logger);

#if defined(WIN32)
        // set ctrl handler for Ctrl + C and Ctrl + Break signal
        SetConsoleCtrlHandler((PHANDLER_ROUTINE)ctrlHandler, TRUE);
#elif defined(LINUX)
        // set ctrl handler for Ctrl + C signal, Ctrl + Break doesnot take effect under LINUX system.
        signal(SIGINT, ctrlPlusCHandler);
#endif
    }

    //! @brief Destructor.
    virtual ~SDPHost() {}

    //! @brief Run the application.
    int run();

protected:
    //! @brief Process command line options.
    int processOptions();

    //! @brief Handler for Ctrl signals.
#if defined(WIN32)
    static BOOL ctrlHandler(DWORD ctrlType);
#elif defined(LINUX)
    static void ctrlPlusCHandler(int msg);
#endif

    //! @brief Show transfer progress.
    static void displayProgress(int percentage, int segmentIndex, int segmentCount);

protected:
    int m_argc;                     //!< Number of command line arguments.
    char **m_argv;                  //!< Command line arguments.
    string_vector_t m_cmdv;         //!< Command line argument vector.
    string m_comPort;               //!< COM port to use.
    int m_comSpeed;                 //!< COM port speed.
    bool m_useUsb;                  //!< Connect over USB HID.
    bool m_useUart;                 //!< Connect over UART.
    uint16_t m_usbVid;              //!< USB VID of the target HID device
    uint16_t m_usbPid;              //!< USB PID of the target HID device
    string m_usbPath;               //!< USB PATH of the target HID device
    uint32_t m_packetTimeoutMs;     //!< Packet timeout in milliseconds.
    StdoutLogger *m_logger;         //!< Singleton logger instance.
};

////////////////////////////////////////////////////////////////////////////////
// Code
////////////////////////////////////////////////////////////////////////////////

//! @brief Print command line usage.
static void printUsage()
{
    printf(k_optionUsage);
    printf(k_commandUsage);
}

#if defined(WIN32)
BOOL SDPHost::ctrlHandler(DWORD ctrlType)
{
    switch (ctrlType)
    {
        // Trap both of Ctrl + C and Ctrl + Break signal.
    case CTRL_C_EVENT:
    case CTRL_BREAK_EVENT:
        Log::warning(
            "\nWarning: Operation canceled!\n- The target device must be reset before sending any further "
            "commands.\n");
        return false;
    default:
        return false;
    }
}
#elif defined(LINUX)
void SDPHost::ctrlPlusCHandler(int msg)
{
    if (msg == SIGINT)
    {
        Log::warning(
            "\nWarning: Operation canceled!\n- The target device must be reset before sending any further commands.\n");
        exit(0);
    }
}
#endif

void SDPHost::displayProgress(int percentage, int segmentIndex, int segmentCount)
{
    Log::info("\r(%d/%d)%d%%", segmentIndex, segmentCount, percentage);
    if (percentage >= 100)
    {
        Log::info(" Completed!\n");
    }
}

int SDPHost::processOptions()
{
    Options options(*m_argv, k_optionsDefinition);

    // If there are no arguments print the usage.
    if (m_argc == 1)
    {
        options.usage(std::cout, usageTrailer);
        printUsage();
        return 0;
    }

    OptArgvIter iter(--m_argc, ++m_argv);

    // Process command line options.
    int optchar;
    const char *optarg;
    while ((optchar = options(iter, optarg)))
    {
        switch (optchar)
        {
        case '?':
            options.usage(std::cout, usageTrailer);
            printUsage();
            return 0;

        case 'v':
            printf("%s %s\n%s\n", k_toolName, k_version, k_copyright);
            return 0;
            break;

        case 'p':
        {
            if (m_useUsb)
            {
                Log::error("Error: You cannot specify both -u and -p options.\n");
                options.usage(std::cout, usageTrailer);
                printUsage();
                return 0;
            }
#if defined(WIN32)
            if (optarg && (string(optarg)[0] == 'c' || string(optarg)[0] == 'C'))
#else
            if (optarg)
#endif
            {
                string_vector_t params = utils::string_split(optarg, ',');
                m_comPort = params[0];
                if (params.size() == 2)
                {
                    int speed = atoi(params[1].c_str());
                    if (speed <= 0)
                    {
                        Log::error("Error: You must specify a valid baud rate with the -p/--port option.\n");
                        options.usage(std::cout, usageTrailer);
                        printUsage();
                        return 0;
                    }
                    m_comSpeed = speed;
                }
            }
            else
            {
                Log::error("Error: You must specify the COM port identifier string with the -p/--port option.\n");
                options.usage(std::cout, usageTrailer);
                printUsage();
                return 0;
            }
            m_useUart = true;
            break;
        }
        case 'u':
        {
            if (m_useUart)
            {
                Log::error("Error: You cannot specify both -u and -p options.\n");
                options.usage(std::cout, usageTrailer);
                printUsage();
                return 0;
            }
            if (optarg)
            {
                string_vector_t params = utils::string_split(optarg, ',');
                uint32_t tempId = 0;
                bool useDefaultVid = true;
                bool useDefaultPid = true;
                uint16_t vid = 0, pid = 0;
                string path;
                if (params.size() == 1)
                {
                    if (utils::stringtoui(params[0].c_str(), tempId) && tempId < 0x00010000)
                    {
                        pid = (uint16_t)tempId;
                        useDefaultPid = false;
                    }
                    else
                    {
                        path = params[0];
                    }
                }
                else if (params.size() == 2)
                {
                    if (utils::stringtoui(params[0].c_str(), tempId) && tempId < 0x00010000)
                    {
                        vid = (uint16_t)tempId;
                        useDefaultVid = false;
                    }
                    else
                    {
                        Log::error("Error: %s is not valid vid for option -u.\n", params[0].c_str());
                        return 0;
                    }
                    if (utils::stringtoui(params[1].c_str(), tempId) && tempId < 0x00010000)
                    {
                        pid = (uint16_t)tempId;
                        useDefaultPid = false;
                    }
                    else
                    {
                        Log::error("Error: %s is not valid pid for option -u.\n", params[1].c_str());
                        return 0;
                    }
                }
                if (!useDefaultPid)
                {
                    m_usbPid = pid;
                }
                if (!useDefaultVid)
                {
                    m_usbVid = vid;
                }
                m_usbPath = path;
            }
            m_useUsb = true;
            break;
        }

        case 'V':
            Log::getLogger()->setFilterLevel(Logger::kDebug);
            break;

        case 'd':
            Log::getLogger()->setFilterLevel(Logger::kDebug2);
            break;

        case 'j':
            Log::getLogger()->setFilterLevel(Logger::kJson);
            break;

        case 't':
            if (optarg)
            {
                uint32_t timeout = 0;
                if (utils::stringtoui(optarg, timeout))
                {
                    m_packetTimeoutMs = timeout;
                }
                else
                {
                    Log::error("Error: %s is not valid for option -t/--timeout.\n", optarg);
                    options.usage(std::cout, usageTrailer);
                    printUsage();
                    return 0;
                }
            }
            break;

            // All other cases are errors.
        default:
            return 1;
        }
    }

    // Treat the rest of the command line as a single bootloader command,
    // possibly with arguments.
    if (iter.index() == m_argc)
    {
        options.usage(std::cout, usageTrailer);
        printUsage();
        return 0;
    }

    // Save command name and arguments.
    for (int i = iter.index(); i < m_argc; ++i)
    {
        m_cmdv.push_back(m_argv[i]);
    }

    // All is well.
    return -1;
}

int SDPHost::run()
{
    // Read command line options.
    int optionsResult;
    if ((optionsResult = processOptions()) != -1)
    {
        return optionsResult;
    }

    int result = 0;
    SDPCommand *cmd = NULL;
    Progress *progress = NULL;

    try
    {
        if (m_cmdv.size())
        {
            // Check for any passed commands and validate command.
            cmd = SDPCommand::create(&m_cmdv);
            if (!cmd)
            {
                std::string msg = format_string("Error: invalid command or arguments '%s", m_cmdv.at(0).c_str());
                string_vector_t::iterator it = m_cmdv.begin();
                for (++it; it != m_cmdv.end(); ++it)
                {
                    msg.append(format_string(" %s", (*it).c_str()));
                }
                msg.append("'\n");
                throw std::runtime_error(msg);
            }

            progress = new Progress(displayProgress, NULL);
            cmd->registerProgress(progress);
        }
        else
        {
            throw std::runtime_error("Internal error: no command\n");
        }

        Packetizer *hostPacketizer;

        if (m_useUsb)
        {
            std::string usbHidSerialNumber;
            UsbHidPeripheral *peripheral = new UsbHidPeripheral(m_usbVid, m_usbPid, usbHidSerialNumber.c_str(), m_usbPath.c_str());
            hostPacketizer = new SDPUsbHidPacketizer(peripheral, m_packetTimeoutMs);
        }
        else // use UART
        {
            UartPeripheral *peripheral = new UartPeripheral(m_comPort.c_str(), m_comSpeed);
            hostPacketizer = new SDPUartPacketizer(peripheral, m_packetTimeoutMs);
        }

        // Send the command.
        cmd->sendTo(*hostPacketizer);

        if (cmd->getResponseValues()->size() > 0)
        {
            // Print command response values.
            cmd->logResponses();

            // Only thing we consider an error is NoResponse
            if (cmd->getResponseValues()->at(0) == SDPCommand::kStatus_NoResponse)
            {
                result = SDPCommand::kStatus_NoResponse;
            }
        }
    }
    catch (exception &e)
    {
        Log::error(e.what());
        result = 1; // return non-zero error code to shell
    }

    if (progress)
    {
        delete progress;
    }

    return result;
}

//! @brief Application entry point.
int main(int argc, char *argv[], char *envp[])
{
    return SDPHost(argc, argv).run();
}


import discord
from disputils import BotEmbedPaginator
from datetime import datetime
from app import db
import user
import jobs

async def paginate(ctx, title, data, page_size=6):
    if len(data) == 0:
        await ctx.send('No data found')
        return
    embeds = []
    for i in range(int((len(data) + 5) / page_size)):
        embeds.append(discord.Embed(title="{} page {}".format(title, i + 1)))

    for i in range(len(data)):
        page = embeds[int(i / page_size)]
        if page.description == discord.Embed.Empty:
            page.description = data[i][1:]
        else:
            page.description += data[i]

    paginator = BotEmbedPaginator(ctx, embeds)
    await paginator.run()

async def view(ctx, type, mine=None):
    fil = {}
    fil['income'] = {'$gt': 0} if type == 'requests' else {'$lte': 0}
    if mine == 'posted':
        fil['accepted'] = 0
        fil['employer'] = ctx.author.id
    elif mine == 'accepted':
        juser = user.JUser(ctx.author.id)
        fil['accepted'] = juser.user_id
    elif mine == 'all':
        pass
    else:
        fil['accepted'] = 0

    if db.jobs.count_documents(fil) == 0:
        await ctx.send("No {} found".format(type))
        return

    data = []
    for j in db.jobs.find(fil).sort('_id', -1):
        job = jobs.Job()
        job.load(j)
        data.append({'name': job.name, 'value': await get_job_output(ctx, job)})
    await paginate(ctx, 'Current {}'.format(type), data)

async def transfer(ctx, source, source_mention, to, to_mention, amount, reason='', job_id=None):
    if amount > 0:
        source.add_jbucks(-1 * amount)
        to.add_jbucks(.9 * amount)
        add_prize_pool(round(.1 * amount, 2))
        await ctx.send('{} has transferred {} JBucks to {}.\n{} of that amount has been taxed and added to the Jelly Prize Pool (JPP)'.format(
            source_mention,
            amount,
            to_mention,
            round(.1 * amount, 2),
        ))
        db.transactions.insert_one({
            'ts': datetime.now(),
            'from': source.user_id,
            'to': to.user_id,
            'amount': amount,
            'reason': reason,
            'job': job_id,
            'jump_url': ctx.message.jump_url,
        })
        source.add_tickets(amount)
    else:
        amount = -1 * amount
        source.add_jbucks(.9 * amount)
        to.add_jbucks(-1 * amount)
        add_prize_pool(.1 * amount)
        await ctx.send('{} has transferred {} JBucks to {}.\n{} of that amount has been taxed and added to the Jelly Prize Pool (JPP)'.format(
            to_mention,
            amount,
            source_mention,
            round(.1 * amount, 2),
        ))
        db.transactions.insert_one({
            'ts': datetime.now(),
            'from': to.user_id,
            'to': source.user_id,
            'amount': -1 * amount,
            'reason': reason,
            'job': job_id,
            'jump_url': ctx.message.jump_url,
        })
        to.add_tickets(amount)


    source.save()
    to.save()

async def get_job_output(ctx, job):
    employer = await get_user(ctx, job.employer)
    if not employer:
        return "Employer no longer available"

    income_str = ""
    if job.income > 0:
        income_str = 'Income: {}'.format(job.income)
    else:
        income_str = 'Cost: {}'.format(-1 * job.income)

    accepted_str = ""
    if job.accepted:
        accepted_by = await get_user(ctx, job.accepted)
        accepted_str = "\nAccepted by: <@{}>".format(accepted_by.id)
    return r"""
        ID: {}
        {}
        {}: {}
        Description: {}{}
    """.format(job._id,
               income_str,
               'Employer' if job.income > 0 else 'Seller',
               '<@{}>'.format(employer.id),
               job.description,
               accepted_str,
    )

async def get_user(ctx, user_id):
    return ctx.bot.get_user(user_id) or await ctx.bot.fetch_user(user_id)

def add_prize_pool(amount):
    db.globals.update_one({'key': 'prize_pool'}, { '$inc': {'value': round(amount, 2)}})

def get_prize_pool():
    return db.globals.find_one({'key': 'prize_pool'}).get('value', 0)
